"""Manager-only plain-form financial reviews; no preview writes."""

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.permissions import ManagerRequiredMixin
from apps.common.forms import StyledForm
from apps.leases.models import Lease
from apps.ledger import deposits
from apps.ledger import finance_reviews as reviews
from apps.ledger.forms import DepositForm
from apps.ledger.services import build_ledger


class ReasonForm(StyledForm):
    reason = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class FinancialReviewView(ManagerRequiredMixin, View):
    action = "apply"
    correcting = False

    def get(self, request, pk, application=None):
        return self.handle(request, pk, application)

    def post(self, request, pk, application=None):
        return self.handle(request, pk, application)

    def handle(self, request, pk, application):
        lease = get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)
        ledger = build_ledger(lease)
        initial = {
            "first_due": timezone.localdate(),
            "agreed_on": timezone.localdate(),
            "mode": "single",
        }
        if ledger.repayment_plans:
            plan = ledger.repayment_plans[-1]
            initial.update(
                mode="monthly" if plan.monthly_amount else "single",
                first_due=plan.first_due,
                monthly_amount=plan.monthly_amount,
                agreement_source=plan.agreement_source,
                explanation=plan.explanation,
            )
        if self.action == "plan":
            form = reviews.RepaymentForm(request.POST or None, initial=initial)
            if self.correcting:
                form.fields["correction_direction"].required = True
                form.fields["correction_amount"].required = True
            else:
                form.fields.pop("correction_direction")
                form.fields.pop("correction_amount")
        elif self.action == "undo":
            form = ReasonForm(request.POST or None)
        else:
            form = reviews.CreditForm(request.POST or None, ledger=ledger)
        review = None
        error = None
        if request.method == "POST":
            try:
                if request.POST.get("action") == "confirm":
                    # A token from another financial workflow cannot be submitted here.
                    from django.core import signing

                    try:
                        payload = signing.loads(
                            request.POST.get("review_token", ""), salt=reviews.SALT, max_age=1800
                        )
                    except signing.BadSignature as exc:
                        raise ValidationError(reviews.STALE) from exc
                    if payload.get("action") != self.action or (
                        self.action == "undo" and payload.get("application") != application
                    ):
                        raise ValidationError(reviews.STALE)
                    if (
                        self.action == "plan"
                        and bool(payload["plan"]["data"].get("correction_direction"))
                        != self.correcting
                    ):
                        raise ValidationError(reviews.STALE)
                    reviews.confirm(pk, token=request.POST["review_token"], actor=request.user)
                    messages.success(
                        request, "Financial update confirmed. No money was transferred."
                    )
                    return redirect("ledger:lease-ledger", pk=pk)
                if request.POST.get("action") == "review" and form.is_valid():
                    review = reviews.prepare(
                        lease,
                        actor=request.user,
                        action=self.action,
                        data=form.cleaned_data,
                        application=application,
                    )
            except ValidationError as exc:
                error = " ".join(exc.messages)
        return render(
            request,
            "management/financial_review.html",
            {
                "lease": lease,
                "ledger": ledger,
                "form": form,
                "review": reviews.display_review(review),
                "error": error,
                "action_kind": self.action,
                "title": "Correct starting debt and review repayments"
                if self.correcting
                else {
                    "apply": "Apply available credit",
                    "undo": "Undo credit application",
                    "plan": "Starting-debt payment dates",
                }[self.action],
            },
        )


class DepositView(ManagerRequiredMixin, View):
    """Record one deposit fact; the register is the audit-able answer to "what is held?"."""

    def get(self, request, pk):
        return self.handle(request, pk)

    def post(self, request, pk):
        return self.handle(request, pk)

    def handle(self, request, pk):
        lease = get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)
        form = DepositForm(
            request.POST or None,
            lease=lease,
            initial={"date": timezone.localdate(), "kind": "RECEIVED"},
        )
        error = None
        if request.method == "POST" and form.is_valid():
            try:
                deposits.record(
                    lease,
                    kind=form.cleaned_data["kind"],
                    amount=form.cleaned_data.get("amount") or 0,
                    date=form.cleaned_data["date"],
                    method=form.cleaned_data.get("method", ""),
                    reference=form.cleaned_data.get("reference", ""),
                    reason=form.cleaned_data.get("reason", ""),
                    evidence=form.cleaned_data.get("evidence"),
                    actor=request.user,
                )
            except ValidationError as exc:
                error = " ".join(exc.messages)
            else:
                messages.success(request, "The security deposit record was added.")
                return redirect("ledger:lease-ledger", pk=lease.pk)
        return render(
            request,
            "management/deposit.html",
            {
                "lease": lease,
                "form": form,
                "error": error,
                "entries": deposits.entries(lease),
                "held": deposits.held(lease),
                "agreed": lease.deposit,
            },
        )
