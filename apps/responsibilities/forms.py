"""Forms for a property's responsibilities and the cycles they are billed in."""

from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.common.forms import StyledForm, StyledModelForm
from apps.responsibilities import services as responsibility_services
from apps.responsibilities.models import PropertyResponsibility, ResponsibilityCycle


class ResponsibilityForm(StyledModelForm):
    """One recurring cost on a property: what it is called and how often it lands."""

    class Meta:
        model = PropertyResponsibility
        fields = ["label", "category", "cycle_months", "is_active", "note"]
        labels = {"is_active": "In use", "cycle_months": "Billing period (months)"}
        help_texts = {
            "label": "What the tenant reads on their statement: Water, Trash, Pruning.",
            "cycle_months": "A quarterly water bill is 3.",
            "note": "Anything the next person should know. Never shown to a tenant.",
        }


class UnitAmountsMixin:
    """The per-unit monthly amounts shared by staging and editing a cycle.

    The amounts are optional, and blank means the share RHP proposes from the property's
    recorded sizes — the same rule the staging screen has always used, so the two screens
    cannot disagree (ADR-014). Type a figure where the division is not a formula: the water
    bill that is not split by floor area, or a unit that is out of the bill, which is a zero.

    The bill is the ceiling. The amounts may add up to *less* than it — a vacant unit's share
    stays with the owner — but never more, and a form that says otherwise is refused here and
    again where the shares are written.
    """

    #: Set by the form that knows the cycle, or the preview the staging form builds.
    cycle = None
    units: list = []

    def add_unit_fields(self, units, amounts=None, proposals=None) -> None:
        self.units = list(units)
        proposals = proposals or {}
        for unit in self.units:
            proposed = proposals.get(unit.pk)
            self.fields[f"unit_{unit.pk}"] = forms.DecimalField(
                label=f"{unit.identifier} a month",
                max_digits=12,
                decimal_places=2,
                min_value=Decimal("0"),
                required=False,
                initial=(amounts or {}).get(unit.pk),
                widget=forms.NumberInput(
                    attrs={"placeholder": f"{proposed:.2f}"} if proposed else None
                ),
                help_text=self._unit_help(unit, proposed),
            )

    def _unit_help(self, unit, proposed=None) -> str:
        share = unit.share_of_property
        size = f"{unit.square_feet:,} sq ft" if unit.square_feet else "no size recorded"
        if share is None:
            return f"{size}. Left blank, the bill is split evenly."
        return f"{size}, {share}% of the property. Left blank, that share is charged."

    def proposal_for(self, unit) -> Decimal | None:
        """What this unit pays if its field is left blank, or ``None`` when RHP cannot say."""
        if self.cycle is None:
            return None
        return responsibility_services.propose_shares(self.cycle).get(unit.pk)

    def amounts(self, units) -> dict[int, Decimal]:
        """The amounts to save, by unit id: what was typed, else that unit's share.

        Blank no longer means "leave it as it was" — it means the proposed share, which is
        what the screen has always told the office it means.
        """
        typed: dict[int, Decimal] = {}
        for unit in units:
            value = self.cleaned_data.get(f"unit_{unit.pk}")
            if value is not None:
                typed[unit.pk] = value
                continue
            proposed = self.proposal_for(unit)
            if proposed is not None:
                typed[unit.pk] = proposed
        return typed

    def check_monthly_total(self, cap: Decimal) -> None:
        """Refuse a division that adds up to more than one month of the bill."""
        if not cap or cap <= Decimal("0"):
            return
        total = sum(self.amounts(self.units).values(), Decimal("0"))
        if total > cap:
            self.add_error(
                None,
                f"The unit amounts add up to {total:,.2f} a month, and this bill is "
                f"{cap:,.2f} a month to divide. Take {total - cap:,.2f} off the amounts.",
            )


class CycleForm(UnitAmountsMixin, StyledForm):
    """Enter a property's bill and allocate its monthly amount to units."""

    starts_on = forms.DateField(
        label="First month covered",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="The billing period starts on the first rent due date on or after this.",
    )
    months = forms.IntegerField(label="Covers (months)", min_value=1, max_value=12, initial=3)
    total_amount = forms.DecimalField(
        label="Property bill total",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="The total billed to the property for this billing period.",
    )
    note = forms.CharField(
        max_length=200, required=False, help_text="The bill's reference, or where it came from."
    )

    def __init__(self, *args, units=(), initial_amounts=None, responsibility=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responsibility = responsibility
        self.add_unit_fields(units, initial_amounts)

    def clean(self):
        """The staging screen checks the ceiling too, against the bill being entered."""
        cleaned = super().clean()
        total_amount = cleaned.get("total_amount")
        months = cleaned.get("months")
        if total_amount is None or not months or self.responsibility is None:
            return cleaned
        # A preview cycle: the proposals need the monthly figure, and nothing is saved to
        # work it out.
        self.cycle = ResponsibilityCycle(
            responsibility=self.responsibility,
            starts_on=cleaned.get("starts_on") or timezone.localdate(),
            months=months,
            total_amount=total_amount,
        )
        self.check_monthly_total(self.cycle.monthly_total)
        return cleaned


class SharesForm(UnitAmountsMixin, StyledForm):
    """Correct the units' monthly amounts on a cycle that is already staged."""

    note = forms.CharField(
        max_length=200,
        required=False,
        help_text="Why the division changed. Recorded with the change.",
    )

    def __init__(self, *args, cycle=None, units=(), initial_amounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cycle = cycle
        self.add_unit_fields(
            units,
            initial_amounts,
            proposals=responsibility_services.propose_shares(cycle) if cycle else None,
        )

    def clean(self):
        cleaned = super().clean()
        if self.cycle is not None:
            self.check_monthly_total(self.cycle.monthly_total)
        return cleaned
