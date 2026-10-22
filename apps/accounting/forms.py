"""Plain forms for the reviewed opening balance sheet."""

from django import forms
from django.forms import formset_factory

from apps.accounting.models import ChartAccount
from apps.common.forms import StyledForm
from apps.properties.models import Property


class OpeningBalanceForm(StyledForm):
    as_of = forms.DateField(
        label="Opening date",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="The date the general ledger starts. No journal is posted before it.",
    )
    note = forms.CharField(
        max_length=500,
        label="Source and review",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Where these balances came from, who prepared them, and who reviewed them.",
    )


class OpeningLineForm(StyledForm):
    account = forms.ModelChoiceField(
        queryset=ChartAccount.objects.none(),
        required=False,
        label="Account",
    )
    property = forms.ModelChoiceField(
        queryset=Property.objects.none(),
        required=False,
        label="Property (optional)",
    )
    debit = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, label="Debit"
    )
    credit = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, label="Credit"
    )
    memo = forms.CharField(max_length=300, required=False, label="Memo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = ChartAccount.objects.filter(
            is_active=True, kind__in=("ASSET", "LIABILITY", "EQUITY")
        ).order_by("code")
        self.fields["property"].queryset = Property.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        debit = cleaned.get("debit") or 0
        credit = cleaned.get("credit") or 0
        if account is None and not debit and not credit:
            return cleaned
        if account is None:
            self.add_error("account", "Choose the account for this amount.")
        if (debit > 0) == (credit > 0):
            raise forms.ValidationError("Use either a debit or a credit on a line, not both.")
        return cleaned


OpeningLineFormSet = formset_factory(OpeningLineForm, extra=8)
