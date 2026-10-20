"""The ledger screens: balances, charges, payments, reversals, adjustments.

Authorization is server-side throughout: financial operations, including reversals
and adjustments, require MANAGER or above. Corrections preserve the original entries.
Nothing here accepts a lease id from a form — the lease comes from the URL and every
queryset is filtered by it.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.permissions import (
    ManagerRequiredMixin,
    TenantAreaMixin,
)
from apps.leases.models import Lease
from apps.leases.views import LeaseDetailView
from apps.leases.workspace import workspace_context
from apps.ledger import services
from apps.ledger.forms import (
    AdjustmentForm,
    ChargeForm,
    PaymentForm,
    ReversePaymentForm,
    VoidPaymentForm,
)
from apps.ledger.models import Charge, ChargeKind, Direction, Payment
from apps.properties.models import Property

logger = logging.getLogger("apps.ledger")

#: A zero amount, for the "nothing is owed on this charge" case.
ZERO = Decimal("0.00")


def _explain(exc: ValidationError) -> str:
    """A ValidationError may carry a dict; the desk wants one readable sentence."""
    return " ".join(exc.messages)


def _charge_count(charges, kind: str, noun: str) -> str:
    """``3 rent charges`` — or nothing at all when that kind was not raised."""
    count = sum(1 for charge in charges if charge.kind == kind)
    if not count:
        return ""
    return f"{count} {noun}{'' if count == 1 else 's'}"


# --- the overview ---------------------------------------------------------


class LedgerOverviewView(ManagerRequiredMixin, TemplateView):
    """Balances across the portfolio: the screen a manager opens in the morning."""

    template_name = "management/ledger_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search = self.request.GET.get("q", "").strip()
        arrears_only = self.request.GET.get("arrears") == "1"
        property_id = self.request.GET.get("property") or None

        rows = services.ledger_rows(search=search, property_id=property_id)
        context.update(
            {
                "rows": [row for row in rows if row.has_arrears] if arrears_only else rows,
                "totals": services.totals(rows),
                "search": search,
                "arrears_only": arrears_only,
                "property_id": property_id,
                "properties": Property.objects.active().order_by("name"),
            }
        )
        return context


class LeaseLedgerView(LeaseDetailView):
    """One tenancy's ledger: what is owed, what happened, and the actions."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(workspace_context(self.request, self.object, section="ledger"))
        return context


# --- actions --------------------------------------------------------------


def _ledger_lease(pk) -> Lease:
    """The lease a ledger action applies to, or 404."""
    return get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)


class GenerateRentChargesView(ManagerRequiredMixin, View):
    """Fill in the missing monthly charges — rent, and NNN on a triple-net lease."""

    def post(self, request, pk):
        lease = _ledger_lease(pk)
        through = services.charges_due()
        try:
            created = services.generate_charges(lease, through=through, actor=request.user)
        except ValidationError as exc:
            messages.error(request, _explain(exc))
            return redirect("ledger:lease-ledger", pk=lease.pk)

        if created:
            parts = [
                _charge_count(created, ChargeKind.RENT, "rent charge"),
                _charge_count(created, ChargeKind.NNN, "NNN charge"),
                _charge_count(created, ChargeKind.RESPONSIBILITY, "property charge"),
            ]
            parts = [part for part in parts if part]
            logger.info("charges created lease=%s count=%s", lease.pk, len(created))
            messages.success(request, f"{', '.join(parts)} posted for {lease.unit.label}.")
        else:
            messages.info(request, f"No due charges were available to post for {lease.unit.label}.")
        return redirect("ledger:lease-ledger", pk=lease.pk)


class ChargeCreateView(ManagerRequiredMixin, View):
    """Add a one-off charge: a recharge, a key replacement, a part month."""

    template_name = "management/ledger_charge_form.html"

    def get(self, request, pk):
        lease = _ledger_lease(pk)
        return render(request, self.template_name, {"lease": lease, "form": ChargeForm()})

    def post(self, request, pk):
        lease = _ledger_lease(pk)
        form = ChargeForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"lease": lease, "form": form})

        data = form.cleaned_data
        try:
            charge = services.create_charge(
                lease,
                description=data["description"],
                amount=data["amount"],
                due_date=data["due_date"],
                actor=request.user,
                kind=ChargeKind.MANUAL,
            )
        except ValidationError as exc:
            form.add_error(None, _explain(exc))
            return render(request, self.template_name, {"lease": lease, "form": form})

        logger.info("charge created pk=%s lease=%s by=%s", charge.pk, lease.pk, request.user.pk)
        messages.success(
            request,
            f"One-time charge of ${charge.amount:,.2f} posted for {lease.unit.label}.",
        )
        return redirect("ledger:lease-ledger", pk=lease.pk)


class PaymentCreateView(ManagerRequiredMixin, View):
    """Record money received, or money expected."""

    template_name = "management/ledger_payment_form.html"

    def get(self, request, pk):
        lease = _ledger_lease(pk)
        return render(request, self.template_name, {"lease": lease, "form": PaymentForm()})

    def post(self, request, pk):
        lease = _ledger_lease(pk)
        form = PaymentForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"lease": lease, "form": form})

        data = form.cleaned_data
        try:
            payment = services.record_payment(
                lease,
                amount=data["amount"],
                payment_date=data["payment_date"],
                method=data["method"],
                status=data["status"],
                external_reference=data["external_reference"],
                notes=data["notes"],
                actor=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, _explain(exc))
            return render(request, self.template_name, {"lease": lease, "form": form})

        logger.info("payment recorded pk=%s lease=%s by=%s", payment.pk, lease.pk, request.user.pk)
        messages.success(
            request,
            f"Payment of ${payment.amount:,.2f} recorded for {lease.unit.label}.",
        )
        return redirect("ledger:lease-ledger", pk=lease.pk)


class PaymentClearView(ManagerRequiredMixin, View):
    """The expected money arrived."""

    def post(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_related("lease"), pk=pk)
        try:
            services.clear_payment(payment, actor=request.user)
            messages.success(
                request,
                f"Payment of ${payment.amount:,.2f} cleared for {payment.lease.unit.label}.",
            )
        except ValidationError as exc:
            messages.error(request, _explain(exc))
        return redirect("ledger:lease-ledger", pk=payment.lease_id)


class PaymentVoidView(ManagerRequiredMixin, View):
    """The expected money never existed."""

    def post(self, request, pk):
        payment = get_object_or_404(Payment.objects.select_related("lease"), pk=pk)
        form = VoidPaymentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "That reason is too long; shorten it and try again.")
            return redirect("ledger:lease-ledger", pk=payment.lease_id)
        try:
            services.void_payment(
                payment, actor=request.user, reason=form.cleaned_data.get("reason", "")
            )
            messages.success(
                request,
                f"Pending payment of ${payment.amount:,.2f} voided for {payment.lease.unit.label}.",
            )
        except ValidationError as exc:
            messages.error(request, _explain(exc))
        return redirect("ledger:lease-ledger", pk=payment.lease_id)


class PaymentReverseView(ManagerRequiredMixin, View):
    """Undo a cleared payment, by adding the offsetting entry."""

    template_name = "management/ledger_reverse.html"

    def get(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related("lease", "lease__unit__property"), pk=pk
        )
        return render(
            request,
            self.template_name,
            {"payment": payment, "lease": payment.lease, "form": ReversePaymentForm()},
        )

    def post(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related("lease", "lease__unit__property"), pk=pk
        )
        form = ReversePaymentForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"payment": payment, "lease": payment.lease, "form": form},
            )
        try:
            reversal = services.reverse_payment(
                payment, reason=form.cleaned_data["reason"], actor=request.user
            )
        except ValidationError as exc:
            form.add_error(None, _explain(exc))
            return render(
                request,
                self.template_name,
                {"payment": payment, "lease": payment.lease, "form": form},
            )

        logger.info(
            "payment reversed original=%s reversal=%s by=%s",
            payment.pk,
            reversal.pk,
            request.user.pk,
        )
        messages.success(
            request,
            f"Payment of ${payment.amount:,.2f} reversed for {payment.lease.unit.label}; "
            "the original entry remains visible.",
        )
        return redirect("ledger:lease-ledger", pk=payment.lease_id)


class ChargeAdjustView(ManagerRequiredMixin, View):
    """Correct a charge, by adding an entry that says what was wrong.

    The amount arrives holding what is **still owed** on the charge, so the
    commonest correction — zeroing a charge that should not have been raised — is
    one submit. A second button fills in the charge's full amount instead, for
    when all of it should be credited even though part was already paid.
    """

    template_name = "management/ledger_adjust.html"

    def _charge(self, pk):
        # A correction cannot be corrected: the lookup refuses one, so a hand-made POST to
        # this URL cannot hide money the way adjusting an adjustment used to (404, not 500).
        return get_object_or_404(
            Charge.objects.select_related("lease", "lease__unit__property").exclude(
                kind=ChargeKind.ADJUSTMENT
            ),
            pk=pk,
        )

    def _line(self, charge):
        """The charge's line in its own ledger: what is settled, what is owed."""
        ledger = services.build_ledger(charge.lease)
        for line in ledger.charges:
            if line.charge.pk == charge.pk:
                return line
        return None

    def _context(self, charge, line, form):
        return {
            "charge": charge,
            "lease": charge.lease,
            "line": line,
            "outstanding": line.outstanding if line else ZERO,
            "form": form,
        }

    def get(self, request, pk):
        charge = self._charge(pk)
        line = self._line(charge)
        initial = {"direction": Direction.DECREASE}
        if line is not None and line.outstanding > ZERO:
            initial["amount"] = line.outstanding
        form = AdjustmentForm(initial=initial)
        return render(request, self.template_name, self._context(charge, line, form))

    def post(self, request, pk):
        charge = self._charge(pk)
        line = self._line(charge)

        data = request.POST
        if data.get("use_full_amount"):
            # Only a reduction makes sense here: crediting the full amount when the
            # entry is meant to increase what is owed would double the debt.
            data = request.POST.copy()
            if data.get("direction", Direction.DECREASE) == Direction.DECREASE:
                data["amount"] = f"{charge.amount:.2f}"

        form = AdjustmentForm(data)
        if not form.is_valid():
            return render(request, self.template_name, self._context(charge, line, form))

        try:
            services.create_adjustment(
                charge,
                direction=form.cleaned_data["direction"],
                amount=form.cleaned_data["amount"],
                reason=form.cleaned_data["reason"],
                actor=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, _explain(exc))
            return render(request, self.template_name, self._context(charge, line, form))

        messages.success(
            request,
            f"Adjustment of ${form.cleaned_data['amount']:,.2f} added to "
            f"{charge.description} for {charge.lease.unit.label}.",
        )
        return redirect("ledger:lease-ledger", pk=charge.lease_id)


# --- The tenant's own money -----------------------------------------------


class TenantPaymentsView(TenantAreaMixin, TemplateView):
    """A tenant's own payment history: what was charged, what was paid.

    Read-only and deliberately thin: it renders `build_ledger`'s numbers, so the
    tenant and the office are looking at the same derivation. There is no id in
    the URL — the session decides whose money this is. Due-date bills and separate
    payments include explicitly labeled canceled expectations, never cash received.
    """

    template_name = "tenancy/payments.html"
    #: Group before pagination: a bill counts as one entry regardless of its components.
    per_page = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lease = Lease.objects.visible_for(self.request.user)
        ledger = services.build_ledger(lease) if lease else None
        statement = ledger.statement_months() if ledger else []

        # One list, so a long tenancy reads a page at a time rather than growing
        # without end: a bill counts as one entry (E2). An out-of-range link
        # falls back rather than 404-ing.
        paginator = Paginator(statement, self.per_page)
        page = paginator.get_page(self.request.GET.get("page"))

        context.update(
            {
                "lease": lease,
                "ledger": ledger,
                "statement": page.object_list,
                "statement_total": paginator.count,
                "page_obj": page if paginator.num_pages > 1 else None,
            }
        )
        return context
