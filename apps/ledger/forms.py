"""Forms for the ledger screens.

A charge, an adjustment, a payment and a reversal are four different acts with
four different permissions, so they are four different forms rather than one
"entry" form with a kind dropdown. The lease is never a form field: it comes from
the URL, so a POST cannot record money against a tenancy the user cannot see.
"""

from decimal import Decimal

from django import forms

from apps.common.forms import StyledModelForm
from apps.ledger.models import Charge, Direction, Payment, PaymentStatus

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
