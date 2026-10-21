"""Lease screens: staff management, and the tenant's own lease.

Authorization is server-side throughout (ADR-003, ADR-007): the staff area is
MANAGER and above, deletion is ADMIN, and the tenant area resolves the lease from
the session so there is no id in a tenant-facing URL to enumerate.
"""

import datetime as dt
import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts.permissions import (
    AdminRequiredMixin,
    ManagerRequiredMixin,
    TenantAreaMixin,
)
from apps.audit.models import AuditAction
from apps.audit.services import events_for_lease, record
from apps.leases import services as lease_services
from apps.leases.forms import (
    ExistingHistoryForm,
    LeaseEndForm,
    LeaseForm,
    LeaseReopenForm,
    LeaseSettleForm,
    LeaseTenantFormSet,
    NnnRateForm,
    OnboardingForm,
    RentPeriodCreateForm,
    RentPeriodForm,
)
from apps.leases.models import (
    FinancialCutover,
    Lease,
    LeaseStatus,
    OnboardingMethod,
    RentPeriod,
)
from apps.leases.workspace import workspace_context
from apps.ledger import services as ledger_services
from apps.ledger.presentation import transaction_history
from apps.properties.models import Unit

logger = logging.getLogger("apps.leases")


# --- Staff: the lease desk -------------------------------------------------

#: Said out loud when changing a lease's template drops its step-up rule (E4). The
#: rule is not "lost": the template that replaced it has none, and a stated lease's
#: amounts are entered on the lease page.
RULE_CLEARED_MESSAGE = (
    "The step-up rule was cleared because this template has none. Add the amounts the "
    "lease names on the lease page, as it writes them."
)


class LeaseListView(ManagerRequiredMixin, ListView):
    template_name = "management/lease_list.html"
    context_object_name = "leases"
    paginate_by = 25

    def get_queryset(self):
        queryset = Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__tenant__tenant_profile"
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(unit__identifier__icontains=search)
                | Q(unit__property__name__icontains=search)
                | Q(lease_tenants__tenant__first_name__icontains=search)
                | Q(lease_tenants__tenant__last_name__icontains=search)
                | Q(lease_tenants__tenant__username__icontains=search)
            ).distinct()
        status = self.request.GET.get("status", "")
        if status in LeaseStatus.values:
            queryset = queryset.filter(status=status)
        if self.request.GET.get("expiring") == "30":
            queryset = queryset.filter(pk__in=Lease.objects.expiring_within(30).values("pk"))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        context["expiring"] = self.request.GET.get("expiring", "")
        context["status_choices"] = LeaseStatus.choices
        return context


class LeaseCreateView(ManagerRequiredMixin, CreateView):
    model = Lease
    form_class = LeaseForm
    template_name = "management/lease_form.html"

    def get_initial(self):
        initial = super().get_initial()
        unit_id = self.request.GET.get("unit", "")
        if unit_id.isdigit() and Unit.objects.filter(pk=unit_id, is_active=True).exists():
            initial["unit"] = int(unit_id)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = LeaseTenantFormSet(self.request.POST or None, instance=Lease())
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = LeaseTenantFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                lease = form.save()
                formset.instance = lease
                formset.save()
            logger.info("lease created pk=%s by=%s", lease.pk, request.user.pk)
            messages.success(
                request,
                f"A draft lease for {lease.unit.label} was created. Activate it when the "
                "paperwork is signed.",
            )
            if form.rule_cleared:
                messages.info(request, RULE_CLEARED_MESSAGE)
            return redirect("leases:lease-detail", pk=lease.pk)

        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class LeaseDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/lease_detail.html"
    context_object_name = "lease"

    def get_queryset(self):
        return Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__tenant__tenant_profile", "rent_periods", "nnn_rates", "documents"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Both financial entry routes use this same authorized workspace.
        context["ledger"] = ledger_services.build_ledger(self.object)
        context["activity_limit"] = settings.RHP_LEDGER_ACTIVITY_LIMIT
        # E1: the rent schedule and the NNN history the rent card renders.
        context["rent_schedule"] = lease_services.schedule_rows(self.object)
        context["nnn_history"] = list(reversed(self.object.nnn_rates_ordered))
        context.update(workspace_context(self.request, self.object))
        context.update(
            transaction_history(
                context["ledger"],
                sort=self.request.GET.get("sort", "newest"),
                history=self.request.GET.get("history", "year"),
            )
        )
        context["history"] = events_for_lease(self.object, limit=25)
        context["can_post_due_charges"] = ledger_services.has_due_charges_to_post(
            self.object, through=ledger_services.charges_due()
        )
        return context


class LeaseUpdateView(ManagerRequiredMixin, UpdateView):
    model = Lease
    form_class = LeaseForm
    template_name = "management/lease_form.html"

    def _refuse_history(self):
        """A closed lease is readable but not editable. Checked after the role gate."""
        if self.object.is_editable:
            return None
        messages.error(
            self.request,
            "This lease has ended and is kept as history. Ask a superadmin if it needs correcting.",
        )
        return redirect("leases:lease-detail", pk=self.object.pk)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._refuse_history() or super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = LeaseTenantFormSet(self.request.POST or None, instance=self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        refusal = self._refuse_history()
        if refusal:
            return refusal

        form = self.get_form()
        formset = LeaseTenantFormSet(request.POST, request.FILES, instance=self.object)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                lease = form.save()
                formset.save()

            logger.info("lease updated pk=%s by=%s", lease.pk, request.user.pk)
            messages.success(request, "The lease was updated.")
            if form.rule_cleared:
                messages.info(request, RULE_CLEARED_MESSAGE)
            return redirect("leases:lease-detail", pk=lease.pk)

        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class LeaseActivateView(ManagerRequiredMixin, View):
    """Draft → active: work out the rent schedule, then raise the first charges.

    For a step-up or triple-net lease this is where the whole term's amounts come
    into being, so nobody has to remember a rise (E1, ADR-013). A fixed lease has
    nothing to generate and behaves exactly as it did before.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        if lease.status != LeaseStatus.DRAFT:
            messages.error(request, "Only a draft lease can be activated.")
            return redirect("leases:lease-detail", pk=lease.pk)
        if not lease.lease_tenants.exists():
            messages.error(request, "Add at least one tenant before activating this lease.")
            return redirect("leases:lease-detail", pk=lease.pk)

        through = ledger_services.charges_due()
        try:
            with transaction.atomic():
                lease.status = LeaseStatus.ACTIVE
                cutover = FinancialCutover.objects.first()
                boundary = (
                    cutover.first_native_date if cutover else timezone.localdate().replace(day=1)
                )
                if lease.start_date >= boundary:
                    lease.billing_start_date = lease.start_date
                    lease.financial_ready = True
                lease.save(
                    update_fields=["status", "billing_start_date", "financial_ready", "updated_at"]
                )
                schedule = lease_services.generate_rent_schedule(lease, actor=request.user)
                created = ledger_services.generate_charges(
                    lease, through=through, actor=request.user
                )
                record(
                    request.user,
                    AuditAction.LEASE_ACTIVATED,
                    obj=lease,
                    lease=lease,
                    summary=f"Lease for {lease.unit.label} activated",
                    template=lease.template,
                    start_date=lease.start_date,
                    end_date=lease.end_date,
                )
        except IntegrityError:
            messages.error(
                request,
                f"{lease.unit.label} already has an active lease. End that one first.",
            )
            return redirect("leases:lease-detail", pk=lease.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("leases:lease-detail", pk=lease.pk)

        details = []
        if schedule.changed:
            details.append(schedule.summary())
        if created:
            count = len(created)
            details.append(
                f"{count} charge{'' if count == 1 else 's'} posted, the latest due "
                f"{through:%d %B %Y}."
            )
        else:
            details.append(f"No charge has fallen due yet ({through:%d %B %Y}).")
        logger.info("lease activated pk=%s by=%s", lease.pk, request.user.pk)
        messages.success(
            request, f"{lease.unit.label} now has an active lease. " + " ".join(details)
        )
        return redirect("leases:lease-detail", pk=lease.pk)


class LeaseEndView(ManagerRequiredMixin, View):
    """End a tenancy: two acts on one screen — the paperwork and the money (P4-Q1, P4-Q2).

    A GET shows the form with today's date and what the close-out would cancel. The first
    submit *reviews* that list for the date actually entered; the second ends the tenancy. Two
    steps rather than one, because changing the end date changes which months are being
    canceled, and the office should see that before it happens.
    """

    template_name = "management/lease_end.html"

    def _lease(self, pk) -> Lease:
        return get_object_or_404(
            Lease.objects.select_related("unit__property").prefetch_related("charges"), pk=pk
        )

    def _context(self, lease, form, *, candidates=None, reviewed=False):
        return {
            "lease": lease,
            "form": form,
            "candidates": candidates if candidates is not None else [],
            "reviewed": reviewed,
            "ledger": ledger_services.build_ledger(lease),
        }

    def get(self, request, pk):
        lease = self._lease(pk)
        if lease.status != LeaseStatus.ACTIVE:
            messages.error(request, "Only a running tenancy can be ended.")
            return redirect("leases:lease-detail", pk=lease.pk)
        form = LeaseEndForm(lease=lease)
        through = form.fields["ended_on"].initial
        return render(
            request,
            self.template_name,
            self._context(
                lease,
                form,
                candidates=ledger_services.close_out_candidates(lease, on=through),
            ),
        )

    def post(self, request, pk):
        lease = self._lease(pk)
        if lease.status != LeaseStatus.ACTIVE:
            messages.error(request, "Only a running tenancy can be ended.")
            return redirect("leases:lease-detail", pk=lease.pk)

        form = LeaseEndForm(request.POST, lease=lease)
        if not form.is_valid():
            return render(request, self.template_name, self._context(lease, form))

        ended_on = form.cleaned_data["ended_on"]
        candidates = list(ledger_services.close_out_candidates(lease, on=ended_on))

        if request.POST.get("stage") != "confirm":
            # First submit: show what this date actually cancels, and ask again.
            return render(
                request,
                self.template_name,
                self._context(lease, form, candidates=candidates, reviewed=True),
            )

        # The screen ticks what to cancel; the service is told what to keep.
        to_cancel = {int(pk) for pk in request.POST.getlist("cancel")}
        keep = [charge.pk for charge in candidates if charge.pk not in to_cancel]
        try:
            adjustments = lease_services.end_lease(
                lease,
                ended_on=ended_on,
                reason=form.cleaned_data["reason"],
                note=form.cleaned_data["note"],
                keep=keep,
                actor=request.user,
            )
        except ValidationError as exc:
            for field, errors in getattr(exc, "message_dict", {}).items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
            if not getattr(exc, "message_dict", None):
                form.add_error(None, exc.messages[0])
            return render(request, self.template_name, self._context(lease, form))

        logger.info("tenancy ended pk=%s by=%s", lease.pk, request.user.pk)
        canceled_label = (
            f"{len(adjustments)} charge(s) closed out" if adjustments else "nothing to close out"
        )
        messages.success(
            request,
            f"The tenancy for {lease.unit.label} ended "
            f"{ended_on:%b} {ended_on.day}, {ended_on.year} — {canceled_label}. "
            "Its money can still be paid and corrected.",
        )
        return redirect("leases:lease-detail", pk=lease.pk)


class LeaseSettleView(ManagerRequiredMixin, View):
    """Close a tenancy's money for good: nothing owed, nothing held (P4-Q1)."""

    template_name = "management/lease_settle.html"

    def _lease(self, pk) -> Lease:
        return get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)

    def get(self, request, pk):
        lease = self._lease(pk)
        refusal = _refuse_settling(request, lease)
        if refusal:
            return redirect("leases:lease-detail", pk=lease.pk)
        return render(
            request,
            self.template_name,
            {
                "lease": lease,
                "form": LeaseSettleForm(),
                "ledger": ledger_services.build_ledger(lease),
            },
        )

    def post(self, request, pk):
        lease = self._lease(pk)
        if _refuse_settling(request, lease):
            return redirect("leases:lease-detail", pk=lease.pk)
        form = LeaseSettleForm(request.POST)
        if form.is_valid():
            try:
                lease_services.settle_account(
                    lease, note=form.cleaned_data["note"], actor=request.user
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
                return render(
                    request,
                    self.template_name,
                    {
                        "lease": lease,
                        "form": form,
                        "ledger": ledger_services.build_ledger(lease),
                    },
                )
            messages.success(request, f"The financial account for {lease.unit.label} was settled.")
            return redirect("leases:lease-detail", pk=lease.pk)
        return render(
            request,
            self.template_name,
            {"lease": lease, "form": form, "ledger": ledger_services.build_ledger(lease)},
        )


class LeaseReopenView(ManagerRequiredMixin, View):
    """Reopen an ended tenancy's financial account without restoring occupancy."""

    template_name = "management/lease_reopen.html"

    def _lease(self, pk) -> Lease:
        return get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)

    def get(self, request, pk):
        lease = self._lease(pk)
        if not lease.is_settled:
            messages.error(request, "Only a settled financial account can be reopened.")
            return redirect("leases:lease-detail", pk=lease.pk)
        return render(request, self.template_name, {"lease": lease, "form": LeaseReopenForm()})

    def post(self, request, pk):
        lease = self._lease(pk)
        form = LeaseReopenForm(request.POST)
        if form.is_valid():
            try:
                lease_services.reopen_account(
                    lease, reason=form.cleaned_data["reason"], actor=request.user
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
                return render(request, self.template_name, {"lease": lease, "form": form})
            messages.success(
                request,
                f"The financial account for {lease.unit.label} was reopened. The tenancy "
                "remains ended.",
            )
            return redirect("leases:lease-detail", pk=lease.pk)
        return render(request, self.template_name, {"lease": lease, "form": form})


def _refuse_settling(request, lease) -> bool:
    """Settling is for a tenancy that has ended; anything else is refused out loud."""
    if lease.status == LeaseStatus.ENDED:
        return False
    messages.error(request, "Only a tenancy that has ended can be settled.")
    return True


# --- E1: the rent schedule and the NNN amount ------------------------------


def _schedule_lease(pk) -> Lease:
    """The lease a schedule action applies to, with what its screen reads."""
    return get_object_or_404(
        Lease.objects.select_related("unit__property").prefetch_related(
            "rent_periods", "nnn_rates"
        ),
        pk=pk,
    )


def _refuse_ended_terms(request, lease) -> bool:
    """An ended tenancy is history: its money stays correctable, its terms do not."""
    if lease.is_editable:
        return False
    messages.error(
        request,
        "This lease has ended. Its terms are history and do not change; its money can still "
        "be corrected on the ledger.",
    )
    return True


class RentScheduleGenerateView(ManagerRequiredMixin, View):
    """Work the term's rent periods out again, leaving charged periods alone."""

    http_method_names = ["post"]

    def post(self, request, pk):
        lease = _schedule_lease(pk)
        if _refuse_ended_terms(request, lease):
            return redirect("leases:lease-detail", pk=lease.pk)
        if not lease.uses_schedule:
            messages.info(
                request,
                "A fixed lease charges one rent for its whole term, so there is no schedule "
                "to generate.",
            )
            return redirect("leases:lease-detail", pk=lease.pk)

        result = lease_services.generate_rent_schedule(lease, actor=request.user)
        if result.locked:
            messages.warning(request, result.summary())
        else:
            messages.success(request, result.summary())
        return redirect("leases:lease-detail", pk=lease.pk)


class RentPeriodUpdateView(ManagerRequiredMixin, View):
    """Set one period's rent by hand — an agreed figure rather than a formula."""

    template_name = "management/lease_rent_period_form.html"

    def _period(self, pk, period_pk) -> RentPeriod:
        """The period, scoped to the lease in the URL so ids cannot be swapped."""
        return get_object_or_404(
            RentPeriod.objects.select_related("lease", "lease__unit__property"),
            pk=period_pk,
            lease_id=pk,
        )

    def _context(self, period, form):
        return {"lease": period.lease, "period": period, "form": form}

    def get(self, request, pk, period_pk):
        period = self._period(pk, period_pk)
        if _refuse_ended_terms(request, period.lease):
            return redirect("leases:lease-detail", pk=period.lease_id)
        return render(
            request,
            self.template_name,
            self._context(period, RentPeriodForm(instance=period)),
        )

    def post(self, request, pk, period_pk):
        period = self._period(pk, period_pk)
        if _refuse_ended_terms(request, period.lease):
            return redirect("leases:lease-detail", pk=period.lease_id)

        form = RentPeriodForm(request.POST)
        if form.is_valid():
            try:
                lease_services.set_rent_period_amount(
                    period,
                    amount=form.cleaned_data["amount"],
                    note=form.cleaned_data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(
                    request, f"Rent from {period.effective_from} is now {period.amount}."
                )
                return redirect("leases:lease-detail", pk=period.lease_id)

        return render(request, self.template_name, self._context(period, form))


class NnnRateStageView(ManagerRequiredMixin, View):
    """Stage the NNN amount that applies from a date (E1, ADR-013)."""

    template_name = "management/lease_nnn_form.html"

    def _context(self, lease, form):
        return {"lease": lease, "form": form, "rates": lease.nnn_rates_ordered}

    def get(self, request, pk):
        lease = _schedule_lease(pk)
        if not lease.uses_nnn:
            messages.error(request, "Only a lease that carries NNN takes an NNN amount.")
            return redirect("leases:lease-detail", pk=lease.pk)
        initial = {"effective_from": lease_services.next_nnn_effective_date(lease)}
        form = NnnRateForm(initial=initial)
        return render(request, self.template_name, self._context(lease, form))

    def post(self, request, pk):
        lease = _schedule_lease(pk)
        if not lease.uses_nnn:
            messages.error(request, "Only a lease that carries NNN takes an NNN amount.")
            return redirect("leases:lease-detail", pk=lease.pk)
        if _refuse_ended_terms(request, lease):
            return redirect("leases:lease-detail", pk=lease.pk)

        form = NnnRateForm(request.POST)
        if form.is_valid():
            try:
                rate = lease_services.stage_nnn_rate(
                    lease,
                    effective_from=form.cleaned_data["effective_from"],
                    monthly_amount=form.cleaned_data["monthly_amount"],
                    note=form.cleaned_data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(
                    request,
                    f"Triple-net (NNN) amount set to ${rate.monthly_amount:,.2f} a month from "
                    f"{rate.effective_from:%b} {rate.effective_from.day}, "
                    f"{rate.effective_from.year}.",
                )
                return redirect("leases:lease-detail", pk=lease.pk)

        return render(request, self.template_name, self._context(lease, form))


class RentPeriodCreateView(ManagerRequiredMixin, View):
    """Add a dated rent amount the lease states — a mid-term step, an extra space (E4)."""

    template_name = "management/lease_rent_period_new.html"

    def _initial(self, lease):
        periods = lease.rent_periods_ordered
        after = periods[-1].effective_from + dt.timedelta(days=1) if periods else lease.start_date
        return {"effective_from": lease_services.first_due_on_or_after(lease, after)}

    def _context(self, lease, form):
        return {"lease": lease, "form": form}

    def get(self, request, pk):
        lease = _schedule_lease(pk)
        if _refuse_ended_terms(request, lease):
            return redirect("leases:lease-detail", pk=lease.pk)
        form = RentPeriodCreateForm(initial=self._initial(lease))
        return render(request, self.template_name, self._context(lease, form))

    def post(self, request, pk):
        lease = _schedule_lease(pk)
        if _refuse_ended_terms(request, lease):
            return redirect("leases:lease-detail", pk=lease.pk)
        form = RentPeriodCreateForm(request.POST)
        if form.is_valid():
            try:
                lease_services.add_rent_period(
                    lease,
                    effective_from=form.cleaned_data["effective_from"],
                    amount=form.cleaned_data["amount"],
                    note=form.cleaned_data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                messages.success(
                    request,
                    f"Rent from {form.cleaned_data['effective_from']} recorded at "
                    f"{form.cleaned_data['amount']}.",
                )
                return redirect("leases:lease-detail", pk=lease.pk)
        return render(request, self.template_name, self._context(lease, form))


class RentPeriodRemoveView(ManagerRequiredMixin, View):
    """Remove a dated amount the office added, while nothing has been charged for it."""

    http_method_names = ["post"]

    def post(self, request, pk, period_pk):
        period = get_object_or_404(
            RentPeriod.objects.select_related("lease"), pk=period_pk, lease_id=pk
        )
        if _refuse_ended_terms(request, period.lease):
            return redirect("leases:lease-detail", pk=period.lease_id)
        try:
            lease_services.remove_rent_period(period, actor=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "That rent amount was removed.")
        return redirect("leases:lease-detail", pk=period.lease_id)


class LeaseOnboardView(ManagerRequiredMixin, View):
    """Bring a tenancy that began before RHP into it, without inventing a debt (E4)."""

    template_name = "management/lease_onboard.html"

    def _existing_history(self, request, lease):
        from apps.leases import history_recovery

        action = request.POST.get("action", "edit")
        form = ExistingHistoryForm(
            request.POST if request.method == "POST" and action != "confirm" else None,
            initial={"billing_start_date": lease.start_date},
        )
        review = None
        recovery_error = None
        if request.method == "POST" and action == "confirm":
            try:
                history_recovery.confirm(
                    lease.pk, token=request.POST.get("review_token", ""), actor=request.user
                )
            except ValidationError as exc:
                recovery_error = " ".join(exc.messages)
            else:
                messages.success(
                    request,
                    "Billing start date confirmed. Existing charges and payments were kept; "
                    "no financial entries were added.",
                )
                return redirect("leases:lease-detail", pk=lease.pk)
        elif request.method == "POST" and action == "review" and form.is_valid():
            try:
                review = history_recovery.prepare(lease, actor=request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
        return render(
            request,
            "management/lease_existing_history.html",
            {
                "lease": lease,
                "form": form,
                "review": review,
                "recovery_error": recovery_error,
                "ledger": ledger_services.build_ledger(lease),
            },
        )

    def _context(self, lease, form):
        return {
            "lease": lease,
            "form": form,
            "charges_through": ledger_services.charges_due(),
            "rent_periods": lease.rent_periods_ordered,
            "nnn_rates": lease.nnn_rates_ordered,
            "expected_months": _months_between(lease.bill_from, timezone.localdate()),
        }

    def get(self, request, pk):
        lease = _schedule_lease(pk)
        if not lease.needs_onboarding:
            messages.info(request, "Prior activity has already been set up for this lease.")
            return redirect("leases:lease-detail", pk=lease.pk)
        if lease.charges.exists():
            return self._existing_history(request, lease)
        form = OnboardingForm(
            initial={
                "method": OnboardingMethod.HISTORY,
                "as_of": timezone.localdate(),
                "billing_start_date": lease.start_date,
            }
        )
        return render(request, self.template_name, self._context(lease, form))

    def post(self, request, pk):
        lease = _schedule_lease(pk)
        if not lease.needs_onboarding:
            messages.info(request, "Prior activity has already been set up for this lease.")
            return redirect("leases:lease-detail", pk=lease.pk)

        if lease.charges.exists() or request.POST.get("history_recovery") == "1":
            return self._existing_history(request, lease)

        form = OnboardingForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                onboarding = lease_services.onboard_lease(
                    lease,
                    method=data["method"],
                    as_of=data["as_of"],
                    received_total=data["received_total"],
                    opening_amount=data["opening_amount"],
                    billing_start_date=data["billing_start_date"],
                    note=data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                logger.info(
                    "lease onboarded pk=%s method=%s by=%s",
                    lease.pk,
                    onboarding.method,
                    request.user.pk,
                )
                messages.success(
                    request,
                    f"Prior activity for {lease.unit.label} was set up using "
                    f"{onboarding.get_method_display().lower()}. Charges are posted from "
                    f"{lease.bill_from:%b} {lease.bill_from.day}, {lease.bill_from.year} onward.",
                )
                return redirect("leases:lease-detail", pk=lease.pk)
        return render(request, self.template_name, self._context(lease, form))


def _months_between(start: dt.date, end: dt.date) -> int:
    """Whole months from one date to another, for the onboarding screen's arithmetic."""
    return max((end.year - start.year) * 12 + (end.month - start.month), 0)


class LeaseDeleteView(AdminRequiredMixin, DeleteView):
    """Deleting is for drafts only; anything that was real stays."""

    model = Lease
    template_name = "management/lease_confirm_delete.html"
    context_object_name = "lease"
    success_url = reverse_lazy("leases:lease-list")

    def _refuse_non_draft(self):
        """Only drafts are deletable. Checked after the role gate."""
        if self.object.status == LeaseStatus.DRAFT:
            return None
        messages.error(
            self.request,
            "An active or ended lease is never deleted — end it instead, so the history stays.",
        )
        return redirect("leases:lease-detail", pk=self.object.pk)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._refuse_non_draft() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._refuse_non_draft() or super().post(request, *args, **kwargs)

    def form_valid(self, form):
        lease = self.object
        response = super().form_valid(form)
        logger.info("lease deleted pk=%s by=%s", lease.pk, self.request.user.pk)
        messages.success(self.request, "The draft lease was deleted.")
        return response


# --- The tenant's own lease ------------------------------------------------


def visible_lease_for(user):
    """The lease a tenant should see. The rule lives on the queryset, so every
    tenant-facing page (the lease, the dashboard, the payment history) resolves it
    the same way."""
    return Lease.objects.visible_for(user)


class TenantLeaseView(TenantAreaMixin, TemplateView):
    """The tenant lease page: their unit, term, rent, co-tenants and document."""

    template_name = "tenancy/lease.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lease = visible_lease_for(self.request.user)
        context["lease"] = lease
        context["lease_is_current"] = bool(lease and lease.is_current)
        context["today"] = timezone.localdate()
        # The tenant reads the same numbers as the staff ledger: one definition,
        # so the two can never disagree (ADR-008).
        context["ledger"] = ledger_services.build_ledger(lease) if lease else None
        context["activity_limit"] = settings.RHP_LEDGER_ACTIVITY_LIMIT
        return context
