"""Forms for the ledger screens.

A charge, an adjustment, a payment and a reversal are four different acts with
four different permissions, so they are four different forms rather than one
"entry" form with a kind dropdown. The lease is never a form field: it comes from
the URL, so a POST cannot record money against a tenancy the user cannot see.
"""

from decimal import Decimal

from django import forms

from apps.common.forms import StyledModelForm
from apps.documents.models import Document
from apps.ledger.models import (
    Charge,
    DepositKind,
    Direction,
    Payment,
    PaymentMethod,
    PaymentStatus,
)

#: The methods a deposit can arrive or leave by.
PaymentMethodChoices = PaymentMethod.choices

#: Recording "money we expect" is allowed; void and reversal are separate acts.
PAYMENT_STATUS_CHOICES = [
    (PaymentStatus.CLEARED, "Cleared — the money is in"),
    (PaymentStatus.PENDING, "Pending — the money is expected"),
]


class ChargeForm(StyledModelForm):
    """A one-off charge on a lease."""

    class Meta:
        model = Charge
        fields = ["description", "amount", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"due_date": "Due date"}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount < Decimal("0.01"):
            raise forms.ValidationError("An amount must be at least one cent.")
        return amount


class AdjustmentForm(forms.Form):
    """A correction to a charge. It creates a new entry; the original stays."""

    direction = forms.ChoiceField(
        choices=Direction.choices,
        initial=Direction.DECREASE,
        label="What this does",
    )
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(
        max_length=200,
        label="Why",
        help_text="Recorded on the entry and in the audit trail.",
    )


class PaymentForm(StyledModelForm):
    """Money received, or money expected."""

    status = forms.ChoiceField(choices=PAYMENT_STATUS_CHOICES, initial=PaymentStatus.CLEARED)

    class Meta:
        model = Payment
        fields = [
            "amount",
            "payment_date",
            "method",
            "status",
            "external_reference",
            "notes",
        ]
        widgets = {"payment_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"external_reference": "Reference", "payment_date": "Date received"}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount < Decimal("0.01"):
            raise forms.ValidationError("An amount must be at least one cent.")
        return amount


class ReversePaymentForm(forms.Form):
    """Undo a payment, by adding the offsetting entry."""

    reason = forms.CharField(
        max_length=200,
        label="Why this is being reversed",
        help_text="Recorded on the reversal and in the audit trail.",
    )


class VoidPaymentForm(forms.Form):
    """Cancel money that was only ever expected."""

    reason = forms.CharField(max_length=200, label="Why (optional)", required=False)


class DepositForm(forms.Form):
    """One deposit fact: received, returned, retained, or explicitly not collected."""

    kind = forms.ChoiceField(
        label="What happened",
        choices=[
            (DepositKind.RECEIVED, "Received and held"),
            (DepositKind.RETURNED, "Returned to the tenant"),
            (DepositKind.WITHHELD, "Retained — deduct from the deposit"),
            (DepositKind.NOT_COLLECTED, "No deposit was collected"),
        ],
    )
    amount = forms.DecimalField(
        label="Amount", max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    date = forms.DateField(
        label="Date", widget=forms.DateInput(attrs={"type": "date"}), required=True
    )
    method = forms.ChoiceField(
        label="Method", choices=[("", "—")] + list(PaymentMethodChoices), required=False
    )
    reference = forms.CharField(label="Reference", max_length=255, required=False)
    reason = forms.CharField(
        label="Reason",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required for a retention, and for saying none was collected.",
    )
    evidence = forms.ModelChoiceField(
        label="Supporting document (optional)",
        queryset=Document.objects.none(),
        required=False,
    )

    def __init__(self, *args, lease, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["evidence"].queryset = Document.objects.filter(
            lease=lease, tenant_visible=False
        )
