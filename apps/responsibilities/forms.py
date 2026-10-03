"""Forms for a property's responsibilities and the cycles they are billed in."""

from decimal import Decimal

from django import forms

from apps.common.forms import StyledForm, StyledModelForm
from apps.responsibilities.models import PropertyResponsibility


class ResponsibilityForm(StyledModelForm):
    """One recurring cost on a property: what it is called and how often it lands."""

    class Meta:
        model = PropertyResponsibility
        fields = ["label", "category", "cycle_months", "is_active", "note"]
        labels = {"is_active": "In use", "cycle_months": "One bill covers (months)"}
        help_texts = {
            "label": "What the tenant reads on their statement: Water, Trash, Pruning.",
            "cycle_months": "A quarterly water bill is 3.",
            "note": "Anything the next person should know. Never shown to a tenant.",
        }


class UnitAmountsMixin:
    """The per-unit monthly amounts shared by staging and editing a cycle.

    The amounts are optional: leave one blank and RHP proposes it from the property's
    recorded sizes. Type one where the division is not a formula — the water bill
    that is not split by floor area, for instance.
    """

    def add_unit_fields(self, units, amounts=None) -> None:
        for unit in units:
            self.fields[f"unit_{unit.pk}"] = forms.DecimalField(
                label=f"{unit.identifier} a month",
                max_digits=12,
                decimal_places=2,
                min_value=Decimal("0"),
                required=False,
                initial=(amounts or {}).get(unit.pk),
                help_text=self._unit_help(unit),
            )

    def _unit_help(self, unit) -> str:
        share = unit.share_of_property
        size = f"{unit.square_feet:,} sq ft" if unit.square_feet else "no size recorded"
        if share is None:
            return f"{size}. Left blank, the bill is split evenly."
        return f"{size}, {share}% of the property. Left blank, that share is charged."

    def amounts(self, units) -> dict[int, Decimal]:
        """The amounts the office typed, by unit id; blanks are left to RHP."""
        typed: dict[int, Decimal] = {}
        for unit in units:
            value = self.cleaned_data.get(f"unit_{unit.pk}")
            if value is not None:
                typed[unit.pk] = value
        return typed


class CycleForm(UnitAmountsMixin, StyledForm):
    """Stage a property's bill: what it was, over how long, and who carries it."""

    starts_on = forms.DateField(
        label="First month covered",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="The cycle runs from the first rent due date on or after this.",
    )
    months = forms.IntegerField(label="Covers (months)", min_value=1, max_value=12, initial=3)
    total_amount = forms.DecimalField(
        label="The property's bill",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="What was billed for the whole property this cycle.",
    )
    note = forms.CharField(
        max_length=200, required=False, help_text="The bill's reference, or where it came from."
    )

    def __init__(self, *args, units=(), initial_amounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_unit_fields(units, initial_amounts)


class SharesForm(UnitAmountsMixin, StyledForm):
    """Correct the units' monthly amounts on a cycle that is already staged."""

    note = forms.CharField(
        max_length=200,
        required=False,
        help_text="Why the division changed. Recorded with the change.",
    )

    def __init__(self, *args, units=(), initial_amounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_unit_fields(units, initial_amounts)
