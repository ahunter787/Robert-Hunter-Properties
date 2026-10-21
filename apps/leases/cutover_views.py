"""Plain-form signed reviews for the installation date and tenancy starting records."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.permissions import AdminRequiredMixin, ManagerRequiredMixin
from apps.leases import cutover
from apps.leases.models import FinancialCutover, Lease, LeaseOpeningRecord
from apps.ledger.finance_reviews import display_review


class FinancialStartView(AdminRequiredMixin, View):
    def get(self, request):
        return render(
            request,
            "management/financial_start.html",
            {"form": cutover.CutoverForm(), "cutover": FinancialCutover.objects.first()},
        )

    def post(self, request):
        form = cutover.CutoverForm(request.POST)
        token = None
        error = None
        if request.POST.get("action") == "confirm":
            try:
                cutover.confirm_date(actor=request.user, token=request.POST.get("review_token", ""))
            except (ValidationError, IntegrityError) as exc:
                error = (
                    " ".join(exc.messages)
                    if isinstance(exc, ValidationError)
                    else "The start date was set in another session. Reload this page."
                )
            else:
                messages.success(
                    request, "RHP financial start date set. No charges or payments were created."
                )
                return redirect("leases:financial-start")
        elif form.is_valid():
            try:
                token = cutover.prepare_date(actor=request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
        return render(
            request,
            "management/financial_start.html",
            {
                "form": form,
                "review_token": token,
                "error": error,
                "cutover": FinancialCutover.objects.first(),
            },
        )


class StartingAccountView(ManagerRequiredMixin, View):
    def get(self, request, pk):
        return self.handle(request, pk)

    def post(self, request, pk):
        return self.handle(request, pk)

    def handle(self, request, pk):
        lease = get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)
        if (lease.charges.exists() or lease.payments.exists()) and lease.needs_onboarding:
            from apps.leases.views import LeaseOnboardView

            return LeaseOnboardView()._existing_history(request, lease)
        opening = LeaseOpeningRecord.objects.filter(lease=lease).first()
        form = cutover.StartingForm(request.POST or None, lease=lease)
        review = None
        error = None
        action = request.POST.get("action", "edit")
        if request.method == "POST" and action == "confirm":
            try:
                cutover.confirm(pk, token=request.POST.get("review_token", ""), actor=request.user)
            except ValidationError as exc:
                error = " ".join(exc.messages)
            else:
                messages.success(
                    request,
                    "Starting account recorded. No payment was received "
                    "or historical bills recreated.",
                )
                return redirect("leases:lease-detail", pk=pk)
        elif request.method == "POST" and action == "review" and form.is_valid():
            try:
                review = cutover.prepare(lease, actor=request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
        return render(
            request,
            "management/starting_account.html",
            {
                "lease": lease,
                "form": form,
                "review": display_review(review),
                "error": error,
                "opening": opening,
                "cutover": FinancialCutover.objects.first(),
            },
        )
