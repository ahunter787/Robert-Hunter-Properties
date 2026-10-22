"""B1 accounting management URLs, mounted under ``/manage/accounting/``."""

from django.urls import path

from apps.accounting import views

app_name = "accounting"

urlpatterns = [
    path("", views.AccountingOverviewView.as_view(), name="overview"),
    path("chart/", views.ChartAccountListView.as_view(), name="chart"),
    path("journals/", views.JournalListView.as_view(), name="journal-list"),
    path("journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal-detail"),
    path("control/", views.ControlTieView.as_view(), name="control"),
    path("opening/", views.OpeningBalanceListView.as_view(), name="opening-list"),
    path("opening/new/", views.OpeningBalanceCreateView.as_view(), name="opening-create"),
    path("bills/", views.VendorBillListView.as_view(), name="bill-list"),
    path("bills/new/", views.VendorBillCreateView.as_view(), name="bill-create"),
    path("bills/<int:pk>/", views.VendorBillDetailView.as_view(), name="bill-detail"),
    path("banks/", views.BankAccountListView.as_view(), name="bank-list"),
    path("banks/new/", views.BankAccountCreateView.as_view(), name="bank-create"),
    path("banks/<int:pk>/", views.BankAccountDetailView.as_view(), name="bank-detail"),
    path(
        "statements/<int:pk>/",
        views.BankStatementDetailView.as_view(),
        name="statement-detail",
    ),
]
