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
from apps.audit.services import events_for_lease
from apps.leases import services as lease_services
from apps.leases.forms import (
    LeaseEndForm,
    LeaseForm,
    LeaseReopenForm,
    LeaseSettleForm,
    LeaseTenantFormSet,
    NnnRateForm,
    RentPeriodCreateForm,
    RentPeriodForm,
)
from apps.leases.models import (
    Lease,
    LeaseStatus,
    RentPeriod,
)
from apps.leases.workspace import workspace_context
from apps.ledger import deposits as ledger_deposits
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

    def get(self, request, *args, **kwargs):
        # RHP has no task queue: reading the lease desk starts any tenancy whose day
        # has arrived. Idempotent, and the management command does the same on deploy.
        lease_services.activate_due_leases(actor=request.user)
        return super().get(request, *args, **kwargs)

    paginate_by = 25

    def get_queryset(self):
        queryset = Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__person__portal_user__tenant_profile"
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(unit__identifier__icontains=search)
                | Q(unit__property__name__icontains=search)
                | Q(lease_tenants__person__first_name__icontains=search)
                | Q(lease_tenants__person__last_name__icontains=search)
                | Q(lease_tenants__person__email__icontains=search)
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

    def get(self, request, *args, **kwargs):
        lease_services.activate_due_leases(actor=request.user)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__person",
            "lease_tenants__tenant__tenant_profile",
            "rent_periods",
            "nnn_rates",
            "documents",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Both financial entry routes use this same authorized workspace.
        context["ledger"] = ledger_services.build_ledger(self.object)
        context["deposit_held"] = ledger_deposits.held(self.object)
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
    """Draft → scheduled or active: work out the rent schedule, then raise what is due.

    For a step-up or triple-net lease this is where the whole term's amounts come
    into being, so nobody has to remember a rise (E1, ADR-013). A lease whose term
    starts later is scheduled, not marked active: an upcoming tenancy takes no
    obligation until its day arrives (M2, ADR-029 D1).
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        try:
            result = lease_services.activate_lease(lease, actor=request.user)
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
        if result.is_future:
            details.append(f"scheduled to start {lease.start_date:%d %B %Y}")
            if result.schedule.changed:
                details.append(result.schedule.summary())
            details.append("No charges are posted until the tenancy starts.")
        else:
            if result.schedule.changed:
                details.append(result.schedule.summary())
            if result.created:
                count = len(result.created)
                details.append(
                    f"{count} charge{'' if count == 1 else 's'} posted, the latest due "
                    f"{result.through:%d %B %Y}."
                )
            else:
                details.append(f"No charge has fallen due yet ({result.through:%d %B %Y}).")
        logger.info(
            "lease activated pk=%s status=%s by=%s",
            lease.pk,
            result.status,
            request.user.pk,
        )
        messages.success(request, f"{lease.unit.label}: " + " ".join(details))
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


class LeaseDeleteView(AdminRequiredMixin, DeleteView):
    """Deleting is for drafts only; anything that was real stays."""

    model = Lease
    template_name = "management/lease_confirm_delete.html"
    context_object_name = "lease"
    success_url = reverse_lazy("leases:lease-list")

    def _refuse_non_draft(self):
        """Drafts, and scheduled tenancies with nothing attached yet, are deletable."""
        if self.object.status == LeaseStatus.DRAFT:
            return None
        if self.object.status == LeaseStatus.FUTURE and not (
            self.object.charges.exists()
            or self.object.payments.exists()
            or self.object.deposit_entries.exists()
            or self.object.documents.exists()
        ):
            return None
        messages.error(
            self.request,
            "This lease is kept as history — end it instead, so the record stays.",
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
        messages.success(self.request, "The lease was deleted.")
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
        lease_services.activate_due_leases(actor=self.request.user)
        lease = visible_lease_for(self.request.user)
        context["lease"] = lease
        context["lease_is_current"] = bool(lease and lease.is_current)
        context["today"] = timezone.localdate()
        # The tenant reads the same numbers as the staff ledger: one definition,
        # so the two can never disagree (ADR-008).
        context["ledger"] = ledger_services.build_ledger(lease) if lease else None
        context["deposit_held"] = ledger_deposits.held(lease) if lease else None
        context["activity_limit"] = settings.RHP_LEDGER_ACTIVITY_LIMIT
        return context
