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
]
