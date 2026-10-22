"""Ledger management URLs, mounted under ``/manage/ledger/``.

Namespaced ``ledger``: every money screen lives in one namespace, and the lease
screens link into it rather than growing their own payment routes.
"""

from django.urls import path

from apps.ledger import views
from apps.ledger.finance_views import DepositView, FinancialReviewView

app_name = "ledger"

urlpatterns = [
    path(
        "leases/<int:pk>/repayment-plan/correct/",
        FinancialReviewView.as_view(action="plan", correcting=True),
        name="opening-correct",
    ),
    path(
        "leases/<int:pk>/credit/apply/",
        FinancialReviewView.as_view(action="apply"),
        name="credit-apply",
    ),
    path(
        "leases/<int:pk>/credit/<int:application>/undo/",
        FinancialReviewView.as_view(action="undo"),
        name="credit-undo",
    ),
    path(
        "leases/<int:pk>/repayment-plan/",
        FinancialReviewView.as_view(action="plan"),
        name="repayment-plan",
    ),
    path("leases/<int:pk>/deposit/", DepositView.as_view(), name="deposit"),
    path("", views.LedgerOverviewView.as_view(), name="overview"),
    path("leases/<int:pk>/", views.LeaseLedgerView.as_view(), name="lease-ledger"),
    path(
        "leases/<int:pk>/rent-charges/",
        views.GenerateRentChargesView.as_view(),
        name="rent-charges",
    ),
    path("leases/<int:pk>/charges/new/", views.ChargeCreateView.as_view(), name="charge-create"),
    path(
        "leases/<int:pk>/payments/new/",
        views.PaymentCreateView.as_view(),
        name="payment-create",
    ),
    path("charges/<int:pk>/adjust/", views.ChargeAdjustView.as_view(), name="charge-adjust"),
    path("payments/<int:pk>/clear/", views.PaymentClearView.as_view(), name="payment-clear"),
    path("payments/<int:pk>/void/", views.PaymentVoidView.as_view(), name="payment-void"),
    path("payments/<int:pk>/reverse/", views.PaymentReverseView.as_view(), name="payment-reverse"),
]
