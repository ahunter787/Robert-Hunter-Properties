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


class VendorBillForm(StyledForm):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), label="Property")
    vendor = forms.ModelChoiceField(queryset=None, required=False, label="Vendor")
    expense_account = forms.ModelChoiceField(
        queryset=ChartAccount.objects.none(), label="Expense account"
    )
    description = forms.CharField(max_length=300, label="What the bill is for")
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    received_on = forms.DateField(
        label="Bill received", widget=forms.DateInput(attrs={"type": "date"})
    )
    due_date = forms.DateField(label="Due date", widget=forms.DateInput(attrs={"type": "date"}))
    note = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.maintenance.models import Vendor

        self.fields["property"].queryset = Property.objects.order_by("name")
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True).order_by("name")
        self.fields["expense_account"].queryset = ChartAccount.objects.filter(
            is_active=True, kind="EXPENSE"
        ).order_by("code")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("due_date") and cleaned.get("received_on"):
            if cleaned["due_date"] < cleaned["received_on"]:
                self.add_error("due_date", "A due date cannot be before the bill date.")
        return cleaned


class VendorPaymentForm(StyledForm):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    paid_on = forms.DateField(label="Paid on", widget=forms.DateInput(attrs={"type": "date"}))
    method = forms.ChoiceField(
        choices=[
            ("ACH", "ACH transfer"),
            ("CHECK", "Check"),
            ("CARD", "Card"),
            ("CASH", "Cash"),
            ("OTHER", "Other"),
        ]
    )
    reference = forms.CharField(max_length=200, required=False, label="Reference")
    note = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class BankAccountForm(StyledForm):
    name = forms.CharField(max_length=100, label="Account name")
    institution = forms.CharField(max_length=120)
    last_four = forms.CharField(max_length=4, label="Last four")
    kind = forms.ChoiceField(choices=[("OPERATING", "Operating"), ("DEPOSIT", "Deposit/escrow")])
    chart_account = forms.ModelChoiceField(
        queryset=ChartAccount.objects.none(), label="Chart account"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["chart_account"].queryset = ChartAccount.objects.filter(
            is_active=True, kind="ASSET", code__startswith="11"
        ).order_by("code")

    def clean_last_four(self):
        value = self.cleaned_data["last_four"].strip()
        if not (value.isdigit() and len(value) == 4):
            raise forms.ValidationError("Enter the last four digits.")
        return value

    def clean_chart_account(self):
        from apps.accounting.models import BankAccount

        chart_account = self.cleaned_data["chart_account"]
        if BankAccount.objects.filter(chart_account=chart_account).exists():
            raise forms.ValidationError("That chart account already has a bank account.")
        return chart_account


class BankMovementForm(StyledForm):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    kind = forms.ChoiceField(
        choices=[("DEPOSIT", "Deposit into bank"), ("WITHDRAWAL", "Withdrawal from bank")]
    )
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    reference = forms.CharField(max_length=200, required=False)
    memo = forms.CharField(max_length=300, required=False)


class BankStatementForm(StyledForm):
    period_start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    period_end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    opening_balance = forms.DecimalField(max_digits=12, decimal_places=2)
    closing_balance = forms.DecimalField(max_digits=12, decimal_places=2)
    source_name = forms.CharField(max_length=200, required=False, label="File name")
    file = forms.FileField(
        label="Statement CSV",
        help_text="Header row with date/description/amount (reference optional).",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("period_start") and cleaned.get("period_end"):
            if cleaned["period_end"] < cleaned["period_start"]:
                self.add_error("period_end", "The period ends before it starts.")
        return cleaned
