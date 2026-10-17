"""The screens that put a property's bills on its units.

E2. Viewing a property's responsibilities is part of the property screen a manager
already reads; **staging a bill and setting the units' shares are admin acts**,
because they decide what tenants are charged (ADR-014). Ids are scoped: a
responsibility or cycle in the URL never reaches another property's records.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.permissions import ManagerRequiredMixin
from apps.leases.models import Lease
from apps.ledger.models import Charge
from apps.properties.models import Property
from apps.responsibilities import services
from apps.responsibilities.forms import CycleForm, ResponsibilityForm, SharesForm
from apps.responsibilities.models import (
    PropertyResponsibility,
    ResponsibilityCycle,
    ResponsibilityShare,
)

logger = logging.getLogger("apps.responsibilities")


def _explain(exc: ValidationError) -> str:
    """A ValidationError may carry a dict; the office wants one readable sentence."""
    return " ".join(exc.messages)


def _property(pk) -> Property:
    return get_object_or_404(Property, pk=pk)


def _units(property_obj):
    """The units a bill is divided between, in a stable order."""
    return list(property_obj.units.order_by("identifier"))


def _responsibility(pk) -> PropertyResponsibility:
    return get_object_or_404(PropertyResponsibility.objects.select_related("property"), pk=pk)


def _cycle(pk) -> ResponsibilityCycle:
    """A cycle, with the responsibility whose money it is."""
    return get_object_or_404(
        ResponsibilityCycle.objects.select_related("responsibility__property"), pk=pk
    )


def _refuse_locked(request, cycle) -> bool:
    """A cycle whose months are charged is history; a correction is an adjustment."""
    if not services.cycle_is_locked(cycle):
        return False
    messages.error(
        request,
        "That cycle's months have already been charged. Correct the charges with adjustments "
        "on the ledger instead.",
    )
    return True


class ResponsibilityCreateView(ManagerRequiredMixin, View):
    """Add a responsibility to a property."""

    template_name = "management/responsibility_form.html"

    def get(self, request, pk):
        property_obj = _property(pk)
        return render(
            request,
            self.template_name,
            {"property": property_obj, "form": ResponsibilityForm(), "responsibility": None},
        )

    def post(self, request, pk):
        property_obj = _property(pk)
        form = ResponsibilityForm(request.POST)
        if form.is_valid():
            responsibility = form.save(commit=False)
            responsibility.property = property_obj
            try:
                services.save_responsibility(
                    responsibility,
                    label=form.cleaned_data["label"],
                    category=form.cleaned_data["category"],
                    cycle_months=form.cleaned_data["cycle_months"],
                    is_active=form.cleaned_data["is_active"],
                    note=form.cleaned_data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, _explain(exc))
            else:
                messages.success(
                    request,
                    f"{responsibility.label} added to {property_obj.name}. Enter its first bill "
                    "when the amount is known.",
                )
                return redirect("portfolio:property-detail", pk=property_obj.pk)

        return render(
            request,
            self.template_name,
            {"property": property_obj, "form": form, "responsibility": None},
        )


class ResponsibilityUpdateView(ManagerRequiredMixin, View):
    """Rename a responsibility, change its cycle length, or stop it."""

    template_name = "management/responsibility_form.html"

    def get(self, request, pk):
        responsibility = _responsibility(pk)
        return render(
            request,
            self.template_name,
            {
                "property": responsibility.property,
                "responsibility": responsibility,
                "form": ResponsibilityForm(instance=responsibility),
            },
        )

    def post(self, request, pk):
        responsibility = _responsibility(pk)
        form = ResponsibilityForm(request.POST, instance=responsibility)
        if form.is_valid():
            try:
                services.save_responsibility(
                    responsibility,
                    label=form.cleaned_data["label"],
                    category=form.cleaned_data["category"],
                    cycle_months=form.cleaned_data["cycle_months"],
                    is_active=form.cleaned_data["is_active"],
                    note=form.cleaned_data["note"],
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, _explain(exc))
            else:
                messages.success(request, f"{responsibility.label} updated.")
                return redirect("portfolio:property-detail", pk=responsibility.property_id)

        return render(
            request,
            self.template_name,
            {
                "property": responsibility.property,
                "responsibility": responsibility,
                "form": form,
            },
        )


def _allocation_state(responsibility):
    """Fingerprint only the facts that affect a reviewed allocation."""
    import hashlib
    import json

    state = {
        "responsibility": [
            responsibility.label,
            responsibility.category,
            responsibility.is_active,
            responsibility.cycle_months,
        ],
        "units": list(
            responsibility.property.units.order_by("pk").values(
                "pk", "identifier", "square_feet", "is_active"
            )
        ),
        "cycles": list(
            responsibility.cycles.order_by("pk").values(
                "pk", "starts_on", "months", "total_amount", "note"
            )
        ),
        "shares": list(
            ResponsibilityShare.objects.filter(cycle__responsibility=responsibility)
            .order_by("pk")
            .values("pk", "cycle_id", "unit_id", "monthly_amount")
        ),
        "charges": list(
            Charge.objects.filter(responsibility=responsibility)
            .order_by("pk")
            .values_list("pk", flat=True)
        ),
        "tenancies": list(
            Lease.objects.filter(unit__property=responsibility.property)
            .order_by("pk")
            .values("pk", "unit_id", "status", "start_date", "end_date")
        ),
    }
    return hashlib.sha256(json.dumps(state, default=str, sort_keys=True).encode()).hexdigest()


def _baseline(responsibility):
    return signing.dumps(_allocation_state(responsibility), salt="expense-baseline")


def _rows(form, saved):
    rows = []
    for unit in form.units:
        rows.append(
            {
                "unit": unit,
                "amount": form[f"unit_{unit.pk}"],
                "percent": form[f"percent_{unit.pk}"],
                "basis": form[f"basis_{unit.pk}"],
                "saved": saved.get(unit.pk, Decimal("0.00")),
                "remainder": str(form["remainder"].value()) == str(unit.pk),
                "vacant": unit.current_lease is None,
            }
        )
    return rows


class AllocationWorkflow(ManagerRequiredMixin, View):
    """A stateless, signed review; navigation and calculation never write."""

    template_name = "management/responsibility_allocation.html"
    new_bill = False

    def objects(self, pk):
        if self.new_bill:
            responsibility = _responsibility(pk)
            return responsibility, None
        cycle = _cycle(pk)
        return cycle.responsibility, cycle

    def get(self, request, pk):
        responsibility, cycle = self.objects(pk)
        if cycle is not None and services.cycle_is_locked(cycle):
            return self.render(request, responsibility, cycle, locked=True)
        if self.new_bill:
            bill = CycleForm(
                prefix="bill",
                initial={
                    "starts_on": services.next_cycle_start(responsibility),
                    "months": responsibility.cycle_months,
                },
            )
            return self.render(request, responsibility, cycle, bill=bill, step="details")
        return self.render(request, responsibility, cycle, step="details")

    def render(
        self,
        request,
        responsibility,
        cycle,
        *,
        bill=None,
        allocation=None,
        step="allocate",
        baseline=None,
        review_token="",
        locked=False,
        draft=(),
    ):
        units = _units(responsibility.property)
        saved = (
            {s.unit_id: s.monthly_amount for s in cycle.shares.all()} if cycle and cycle.pk else {}
        )
        if cycle is not None and allocation is None:
            allocation = SharesForm(cycle=cycle, units=units, initial_amounts=saved)
        if allocation is not None and not allocation.is_bound:
            allocation.worksheet = services.allocate_monthly(
                cycle,
                units=units,
                amounts={u.pk: saved.get(u.pk, Decimal("0.00")) for u in units},
                percentages={},
                bases={u.pk: "amount" for u in units},
            )
        worksheet = allocation.worksheet if allocation else None
        if worksheet:
            proposed = {row.unit.pk: row for row in worksheet.rows}
            review_rows = [
                {
                    "unit": u,
                    "amount": proposed[u.pk].amount,
                    "percent": proposed[u.pk].percent,
                    "saved": saved.get(u.pk, Decimal("0.00")),
                    "change": proposed[u.pk].amount - saved.get(u.pk, Decimal("0.00")),
                    "vacant": u.current_lease is None,
                }
                for u in units
            ]
        else:
            review_rows = []
        vacancy = sum((r["amount"] for r in review_rows if r["vacant"]), Decimal("0.00"))
        return render(
            request,
            self.template_name,
            {
                "responsibility": responsibility,
                "property": responsibility.property,
                "cycle": cycle,
                "new_bill": self.new_bill,
                "bill": bill,
                "allocation": allocation,
                "rows": _rows(allocation, saved) if allocation else [],
                "worksheet": worksheet,
                "review_rows": review_rows,
                "rhpshare": worksheet.left + vacancy if worksheet else None,
                "rounding": cycle.monthly_total * cycle.months - cycle.total_amount
                if cycle
                else None,
                "step": step,
                "baseline": baseline or _baseline(responsibility),
                "review_token": review_token,
                "locked": locked,
                "draft": draft,
            },
        )

    def post(self, request, pk):
        responsibility, cycle = self.objects(pk)
        if cycle is not None and services.cycle_is_locked(cycle):
            return self.render(request, responsibility, cycle, locked=True)
        action = request.POST.get("action", "calculate")
        bill = CycleForm(request.POST, prefix="bill") if self.new_bill else None
        if bill is not None:
            if not bill.is_valid() or action == "details":
                draft = [
                    (key, value)
                    for key, value in request.POST.items()
                    if key.startswith(("unit_", "percent_", "basis_"))
                    or key in ("remainder", "note")
                ]
                return self.render(
                    request,
                    responsibility,
                    cycle,
                    bill=bill,
                    step="details",
                    draft=draft,
                    baseline=request.POST.get("baseline"),
                )
            cycle = ResponsibilityCycle(responsibility=responsibility, **bill.cleaned_data)
        units = _units(responsibility.property)
        saved = {s.unit_id: s.monthly_amount for s in cycle.shares.all()} if cycle.pk else {}
        if action == "allocate" and not request.POST.get(
            "basis_" + str(units[0].pk) if units else "basis_"
        ):
            allocation = SharesForm(cycle=cycle, units=units, initial_amounts=saved)
            return self.render(
                request,
                responsibility,
                cycle,
                bill=bill,
                allocation=allocation,
                baseline=request.POST.get("baseline"),
            )
        allocation = SharesForm(request.POST, cycle=cycle, units=units)
        valid = allocation.is_valid()
        baseline = request.POST.get("baseline", "")
        if action in ("review", "save") and not valid:
            try:
                if signing.loads(
                    baseline, salt="expense-baseline", max_age=7200
                ) != _allocation_state(responsibility):
                    allocation.add_error(
                        None, "This bill or its units changed. Review the updated allocation."
                    )
                    baseline = _baseline(responsibility)
            except signing.BadSignature:
                allocation.add_error(
                    None, "This review expired or is invalid. Review the allocation again."
                )
                baseline = _baseline(responsibility)
        if valid and action in ("review", "save"):
            try:
                with transaction.atomic():
                    # Same parent lock as set_shares, stage_cycle and charge generation.
                    PropertyResponsibility.objects.select_for_update().get(pk=responsibility.pk)
                    state = _allocation_state(responsibility)
                    if signing.loads(baseline, salt="expense-baseline", max_age=7200) != state:
                        raise ValidationError(
                            "This bill or its units changed. "
                            "Review the current saved amounts before saving."
                        )
                    if cycle.pk:
                        services._refuse_locked(cycle)
                    elif responsibility.cycles.filter(starts_on=cycle.starts_on).exists():
                        raise ValidationError(
                            "A bill already starts on this date. "
                            "Open that bill to change its allocation."
                        )
                    payload = {
                        "state": state,
                        "actor": request.user.pk,
                        "responsibility": responsibility.pk,
                        "cycle": cycle.pk,
                        "bill": [
                            str(cycle.starts_on),
                            cycle.months,
                            str(cycle.total_amount),
                            cycle.note,
                        ],
                        "amounts": {str(k): str(v) for k, v in allocation.amounts().items()},
                        "note": allocation.cleaned_data["note"],
                    }
                    if action == "review":
                        token = signing.dumps(payload, salt="expense-review")
                        return self.render(
                            request,
                            responsibility,
                            cycle,
                            bill=bill,
                            allocation=allocation,
                            step="review",
                            baseline=baseline,
                            review_token=token,
                        )
                    reviewed = signing.loads(
                        request.POST.get("review_token", ""), salt="expense-review", max_age=7200
                    )
                    if reviewed != payload:
                        raise ValidationError(
                            "The allocation changed after review. Review it again before saving."
                        )
                    if self.new_bill:
                        services.stage_cycle(
                            responsibility,
                            **bill.cleaned_data,
                            amounts_by_unit=allocation.amounts(),
                            allocation_note=allocation.cleaned_data["note"],
                            actor=request.user,
                        )
                    else:
                        services.set_shares(
                            cycle,
                            allocation.amounts(),
                            note=allocation.cleaned_data["note"],
                            actor=request.user,
                        )
            except (signing.BadSignature, ValidationError) as exc:
                message = (
                    "This review expired or is invalid. Review the allocation again."
                    if isinstance(exc, signing.BadSignature)
                    else _explain(exc)
                )
                allocation.add_error(None, message)
                baseline = _baseline(responsibility)
            else:
                messages.success(
                    request,
                    f"{responsibility.label} allocation saved for {responsibility.property.name}. "
                    "No tenant charges were posted.",
                )
                return redirect("portfolio:property-detail", pk=responsibility.property_id)
        if allocation.worksheet and action != "save":
            # Render the canonical pair, never a stale dollar field beside a new percentage.
            data = allocation.data.copy()
            for line in allocation.worksheet.rows:
                data[f"unit_{line.unit.pk}"] = str(line.amount)
                data[f"percent_{line.unit.pk}"] = str(line.percent)
                # Normalize computed values to exact cents so display rounding cannot drift.
                data[f"basis_{line.unit.pk}"] = (
                    "excluded"
                    if allocation.cleaned_data[f"basis_{line.unit.pk}"] == "excluded"
                    and request.POST.get("allocation_method", "custom") == "custom"
                    else "amount"
                )
            data["allocation_method"] = "custom"
            normalized = SharesForm(data, cycle=cycle, units=units)
            normalized.is_valid()
            for error in allocation.non_field_errors():
                if error not in normalized.non_field_errors():
                    normalized.add_error(None, error)
            allocation = normalized
        return self.render(
            request, responsibility, cycle, bill=bill, allocation=allocation, baseline=baseline
        )


class CycleStageView(AllocationWorkflow):
    new_bill = True


class CycleSharesView(AllocationWorkflow):
    pass


class CycleShareCalculateView(CycleSharesView):
    """Compatibility URL: calculation remains a preview, regardless of posted action."""

    http_method_names = ["post"]

    def post(self, request, pk):
        data = request.POST.copy()
        data["action"] = "calculate"
        request.POST = data
        return super().post(request, pk)
