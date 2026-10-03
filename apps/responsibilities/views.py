"""The screens that put a property's bills on its units.

E2. Viewing a property's responsibilities is part of the property screen a manager
already reads; **staging a bill and setting the units' shares are admin acts**,
because they decide what tenants are charged (ADR-014). Ids are scoped: a
responsibility or cycle in the URL never reaches another property's records.
"""

import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.permissions import AdminRequiredMixin
from apps.properties.models import Property
from apps.responsibilities import services
from apps.responsibilities.forms import CycleForm, ResponsibilityForm, SharesForm
from apps.responsibilities.models import PropertyResponsibility, ResponsibilityCycle

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


class ResponsibilityCreateView(AdminRequiredMixin, View):
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
                    f"{responsibility.label} added to {property_obj.name}. Stage its first bill "
                    "to charge it.",
                )
                return redirect("portfolio:property-detail", pk=property_obj.pk)

        return render(
            request,
            self.template_name,
            {"property": property_obj, "form": form, "responsibility": None},
        )


class ResponsibilityUpdateView(AdminRequiredMixin, View):
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


class CycleStageView(AdminRequiredMixin, View):
    """Stage a property bill: its total, its months, and the units' shares."""

    template_name = "management/responsibility_cycle_form.html"

    def _context(self, responsibility, form, units):
        latest = responsibility.cycles_ordered()
        return {
            "responsibility": responsibility,
            "property": responsibility.property,
            "form": form,
            "units": units,
            "current_cycle": responsibility.current_cycle(),
            "next_cycle": responsibility.next_cycle(),
            "previous_cycle": latest[-1] if latest else None,
        }

    def get(self, request, pk):
        responsibility = _responsibility(pk)
        units = _units(responsibility.property)
        previous = responsibility.cycles_ordered()
        amounts = {}
        if previous:
            amounts = {share.unit_id: share.monthly_amount for share in previous[-1].shares.all()}
        form = CycleForm(
            units=units,
            initial={
                "starts_on": services.next_cycle_start(responsibility),
                "months": responsibility.cycle_months,
            },
            initial_amounts=amounts,
        )
        return render(request, self.template_name, self._context(responsibility, form, units))

    def post(self, request, pk):
        responsibility = _responsibility(pk)
        units = _units(responsibility.property)
        form = CycleForm(request.POST, units=units)
        if form.is_valid():
            try:
                cycle = services.stage_cycle(
                    responsibility,
                    starts_on=form.cleaned_data["starts_on"],
                    total_amount=form.cleaned_data["total_amount"],
                    months=form.cleaned_data["months"],
                    note=form.cleaned_data["note"],
                    amounts_by_unit=form.amounts(units),
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, _explain(exc))
            else:
                logger.info("responsibility cycle staged pk=%s by=%s", cycle.pk, request.user.pk)
                messages.success(
                    request,
                    f"{responsibility.label} staged for {cycle.months} month"
                    f"{'' if cycle.months == 1 else 's'} from {cycle.starts_on}. "
                    "Create charges on each tenancy's ledger to bill it.",
                )
                return redirect("portfolio:property-detail", pk=responsibility.property_id)

        return render(request, self.template_name, self._context(responsibility, form, units))


class CycleSharesView(AdminRequiredMixin, View):
    """Correct the units' monthly amounts on a cycle already staged."""

    template_name = "management/responsibility_shares_form.html"

    def _context(self, cycle, form, units):
        return {
            "cycle": cycle,
            "responsibility": cycle.responsibility,
            "property": cycle.responsibility.property,
            "form": form,
            "units": units,
        }

    def get(self, request, pk):
        cycle = _cycle(pk)
        units = _units(cycle.responsibility.property)
        amounts = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
        return render(
            request,
            self.template_name,
            self._context(cycle, SharesForm(units=units, initial_amounts=amounts), units),
        )

    def post(self, request, pk):
        cycle = _cycle(pk)
        units = _units(cycle.responsibility.property)
        form = SharesForm(request.POST, units=units)
        if form.is_valid():
            # A blank field leaves that unit's amount as it is; a typed figure —
            # including a zero, which takes the unit out — is what changes (ADR-014).
            amounts = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
            amounts.update(form.amounts(units))
            try:
                services.set_shares(
                    cycle, amounts, note=form.cleaned_data["note"], actor=request.user
                )
            except ValidationError as exc:
                form.add_error(None, _explain(exc))
            else:
                messages.success(
                    request, f"{cycle.responsibility.label} from {cycle.starts_on} updated."
                )
                return redirect("portfolio:property-detail", pk=cycle.responsibility.property_id)

        return render(request, self.template_name, self._context(cycle, form, units))
