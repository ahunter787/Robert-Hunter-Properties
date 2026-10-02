"""Lease screens: staff management, and the tenant's own lease.

Authorization is server-side throughout (ADR-003, ADR-007): the staff area is
MANAGER and above, deletion is ADMIN, and the tenant area resolves the lease from
the session so there is no id in a tenant-facing URL to enumerate.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
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
    TenantRequiredMixin,
)
from apps.leases.forms import LeaseForm, LeaseTenantFormSet
from apps.leases.models import Lease, LeaseStatus
from apps.ledger import services as ledger_services
from apps.properties.models import Unit

logger = logging.getLogger("apps.leases")


def document_response(field_file) -> FileResponse:
    """Serve an uploaded document from the application, never from the proxy."""
    field_file.open("rb")
    response = FileResponse(field_file)
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- Staff: the lease desk -------------------------------------------------


class LeaseListView(ManagerRequiredMixin, ListView):
    template_name = "management/lease_list.html"
    context_object_name = "leases"
    paginate_by = 25

    def get_queryset(self):
        queryset = Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__tenant"
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
            return redirect("leases:lease-detail", pk=lease.pk)

        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class LeaseDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/lease_detail.html"
    context_object_name = "lease"

    def get_queryset(self):
        return Lease.objects.select_related("unit__property").prefetch_related(
            "lease_tenants__tenant"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The ledger is a summary here; the full screen lives in apps.ledger.
        context["ledger"] = ledger_services.build_ledger(self.object)
        context["activity_limit"] = settings.RHP_LEDGER_ACTIVITY_LIMIT
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
            previous_document = (
                Lease.objects.filter(pk=self.object.pk).values_list("lease_file", flat=True).first()
                or ""
            )
            storage = self.object.lease_file.storage
            with transaction.atomic():
                lease = form.save()
                formset.save()

            current_document = lease.lease_file.name if lease.lease_file else ""
            if previous_document and previous_document != current_document:
                storage.delete(previous_document)

            logger.info("lease updated pk=%s by=%s", lease.pk, request.user.pk)
            messages.success(request, "The lease was updated.")
            return redirect("leases:lease-detail", pk=lease.pk)

        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class LeaseActivateView(ManagerRequiredMixin, View):
    """Draft → active. The database refuses a second active lease on the unit."""

    http_method_names = ["post"]

    def post(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        if lease.status != LeaseStatus.DRAFT:
            messages.error(request, "Only a draft lease can be activated.")
            return redirect("leases:lease-detail", pk=lease.pk)
        if not lease.lease_tenants.exists():
            messages.error(request, "Add at least one tenant before activating this lease.")
            return redirect("leases:lease-detail", pk=lease.pk)

        lease.status = LeaseStatus.ACTIVE
        try:
            with transaction.atomic():
                lease.save(update_fields=["status", "updated_at"])
        except IntegrityError:
            messages.error(
                request,
                f"{lease.unit.label} already has an active lease. End that one first.",
            )
            return redirect("leases:lease-detail", pk=lease.pk)

        logger.info("lease activated pk=%s by=%s", lease.pk, request.user.pk)
        messages.success(request, f"{lease.unit.label} now has an active lease.")
        return redirect("leases:lease-detail", pk=lease.pk)


class LeaseEndView(ManagerRequiredMixin, View):
    """Active → ended. Ended leases stay readable and stop being editable."""

    http_method_names = ["post"]

    def post(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        if lease.status != LeaseStatus.ACTIVE:
            messages.error(request, "Only an active lease can be ended.")
            return redirect("leases:lease-detail", pk=lease.pk)

        lease.status = LeaseStatus.ENDED
        lease.save(update_fields=["status", "updated_at"])
        logger.info("lease ended pk=%s by=%s", lease.pk, request.user.pk)
        messages.success(
            request, f"The lease for {lease.unit.label} was ended and kept as history."
        )
        return redirect("leases:lease-detail", pk=lease.pk)


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


class LeaseDocumentView(ManagerRequiredMixin, View):
    """The lease document for staff, served through the application."""

    http_method_names = ["get"]

    def get(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        if not lease.lease_file:
            raise Http404("This lease has no document attached.")
        return document_response(lease.lease_file)


# --- The tenant's own lease ------------------------------------------------


def visible_lease_for(user):
    """The lease a tenant should see: the current one, otherwise the latest.

    A draft is the office's working copy — its rent and term can still change —
    so a tenant never sees one. They see nothing until the tenancy is activated,
    and the page says so rather than showing terms that may not be agreed.
    """
    leases = (
        Lease.objects.for_tenant(user)
        .exclude(status=LeaseStatus.DRAFT)
        .select_related("unit__property")
        .prefetch_related("lease_tenants__tenant")
    )
    current = leases.current().first()
    if current is not None:
        return current
    return leases.order_by("-end_date", "-start_date").first()


class TenantLeaseView(TenantRequiredMixin, TemplateView):
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


class TenantLeaseDocumentView(TenantRequiredMixin, View):
    """Serve the tenant's own lease document.

    The resource is implied by the session, so there is no id in the URL that
    could be changed to reach somebody else's file.
    """

    http_method_names = ["get"]

    def get(self, request):
        lease = visible_lease_for(request.user)
        if lease is None or not lease.lease_file:
            raise Http404("There is no lease document on your account.")
        return document_response(lease.lease_file)
