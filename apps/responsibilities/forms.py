"""Explicit bill details and monthly allocation forms (ADR-014)."""

from decimal import Decimal

from django import forms

from apps.common.forms import StyledForm, StyledModelForm
from apps.responsibilities import services
from apps.responsibilities.models import PropertyResponsibility


class ResponsibilityForm(StyledModelForm):
    class Meta:
        model = PropertyResponsibility
        fields = ["label", "category", "cycle_months", "is_active", "note"]
        labels = {"is_active": "In use", "cycle_months": "Billing period (months)"}
        help_texts = {
            "label": "What the tenant reads on their statement: Water, Trash, Pruning.",
            "cycle_months": "A quarterly water bill is 3.",
            "note": "Anything the next person should know. Never shown to a tenant.",
        }


class CycleForm(StyledForm):
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
    )
    note = forms.CharField(
        max_length=200, required=False, help_text="The bill's reference, or where it came from."
    )


class SharesForm(StyledForm):
    remainder = forms.ChoiceField(label="Send the remaining monthly amount to…", initial="rhp")
    note = forms.CharField(
        max_length=200,
        required=False,
        label="Allocation note",
        help_text="Explain the allocation or change. Not shown to tenants.",
    )

    def __init__(self, *args, cycle, units, initial_amounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cycle = cycle
        self.units = list(units)
        self.worksheet = None
        self.fields["remainder"].choices = [("rhp", "RHP")] + [
            (str(unit.pk), unit.identifier) for unit in self.units
        ]
        for unit in self.units:
            amount = (initial_amounts or {}).get(unit.pk, Decimal("0.00"))
            self.fields[f"unit_{unit.pk}"] = forms.DecimalField(
                label=f"{unit.identifier}: monthly amount",
                max_digits=12,
                decimal_places=2,
                min_value=Decimal("0"),
                required=False,
                initial=amount,
                widget=forms.NumberInput(
                    attrs={"class": "rhp-field", "step": "0.01", "data-allocation-input": "amount"}
                ),
            )
            self.fields[f"percent_{unit.pk}"] = forms.DecimalField(
                label=f"{unit.identifier}: percentage",
                max_digits=6,
                decimal_places=2,
                min_value=Decimal("0"),
                max_value=Decimal("100"),
                required=False,
                initial=services.share_percent(amount, cycle.monthly_total),
                widget=forms.NumberInput(
                    attrs={"class": "rhp-field", "step": "0.01", "data-allocation-input": "percent"}
                ),
            )
            self.fields[f"basis_{unit.pk}"] = forms.ChoiceField(
                label=f"{unit.identifier}: calculate using",
                initial="amount",
                choices=[
                    ("amount", "Monthly dollars"),
                    ("percent", "Percentage"),
                    ("excluded", "Exclude from this bill"),
                ],
                widget=forms.Select(attrs={"class": "rhp-field", "data-allocation-basis": ""}),
            )
            recipient = (
                self.data.get("remainder") if self.is_bound else self.initial.get("remainder")
            )
            if str(unit.pk) == str(recipient):
                for key in (f"unit_{unit.pk}", f"percent_{unit.pk}"):
                    self.fields[key].widget.attrs["readonly"] = True

    def clean(self):
        cleaned = super().clean()
        method = self.data.get("allocation_method", "custom")
        remainder = cleaned.get("remainder", "rhp")
        # Only the selected input is authoritative. Stale/half-typed values in
        # its counterpart, excluded rows, or the remainder row are not inputs.
        for unit in self.units:
            basis = cleaned.get(f"basis_{unit.pk}")
            for key, kind in ((f"unit_{unit.pk}", "amount"), (f"percent_{unit.pk}", "percent")):
                if method != "custom" or str(unit.pk) == remainder or basis != kind:
                    self._errors.pop(key, None)
        if method == "custom":
            for unit in self.units:
                if str(unit.pk) == remainder:
                    continue
                basis = cleaned.get(f"basis_{unit.pk}")
                key = f"percent_{unit.pk}" if basis == "percent" else f"unit_{unit.pk}"
                if (
                    basis in ("amount", "percent")
                    and cleaned.get(key) is None
                    and key not in self.errors
                ):
                    self.add_error(key, "Enter a value, or explicitly exclude this unit.")
        if self.errors:
            return cleaned
        try:
            self.worksheet = services.allocate_monthly(
                self.cycle,
                units=self.units,
                amounts={u.pk: cleaned.get(f"unit_{u.pk}") for u in self.units},
                percentages={u.pk: cleaned.get(f"percent_{u.pk}") for u in self.units},
                bases={u.pk: cleaned[f"basis_{u.pk}"] for u in self.units},
                remainder=remainder,
                method=method,
            )
            if self.worksheet.over:
                self.add_error(
                    None, f"Allocations exceed the monthly bill by ${self.worksheet.over:,.2f}."
                )
        except forms.ValidationError as exc:
            self.add_error(None, exc)
        return cleaned

    def amounts(self, units=None):
        return {row.unit.pk: row.amount for row in self.worksheet.rows}
