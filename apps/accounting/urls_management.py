"""B1 accounting management URLs, mounted under ``/manage/accounting/``."""

from django.urls import path

from apps.accounting import report_views, views

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
    path("reports/", report_views.ReportIndexView.as_view(), name="report-index"),
    path(
        "reports/income/",
        report_views.IncomeStatementView.as_view(),
        name="report-income",
    ),
    path(
        "reports/balance-sheet/",
        report_views.BalanceSheetView.as_view(),
        name="report-balance-sheet",
    ),
    path("reports/cash-flow/", report_views.CashFlowView.as_view(), name="report-cash-flow"),
    path("reports/schedule-e/", report_views.ScheduleEView.as_view(), name="report-schedule-e"),
    path("reports/ar-aging/", report_views.ARAgingView.as_view(), name="report-ar-aging"),
    path("reports/ap-aging/", report_views.APAgingView.as_view(), name="report-ap-aging"),
    path(
        "reports/deposits/",
        report_views.DepositRegisterView.as_view(),
        name="report-deposits",
    ),
    path("closing/", views.ClosingView.as_view(), name="closing"),
    path("owner/", views.OwnerTransactionListView.as_view(), name="owner-list"),
    path("exports/", views.ExportIndexView.as_view(), name="export-index"),
    path(
        "exports/journal.csv",
        views.JournalExportView.as_view(),
        {"kind": "csv"},
        name="export-journal-csv",
    ),
    path(
        "exports/journal.txt",
        views.JournalExportView.as_view(),
        {"kind": "text"},
        name="export-journal-text",
    ),
]
