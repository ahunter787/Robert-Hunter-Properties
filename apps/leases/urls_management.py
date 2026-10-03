"""Lease management URLs, mounted under ``/manage/``.

Namespaced ``leases`` rather than reusing ``manage``: two ``include()`` calls
sharing one namespace would leave the earlier set of routes unreachable through
``reverse()``.
"""

from django.urls import path

from apps.leases import views

app_name = "leases"

urlpatterns = [
    path("leases/", views.LeaseListView.as_view(), name="lease-list"),
    path("leases/new/", views.LeaseCreateView.as_view(), name="lease-create"),
    path("leases/<int:pk>/", views.LeaseDetailView.as_view(), name="lease-detail"),
    path("leases/<int:pk>/edit/", views.LeaseUpdateView.as_view(), name="lease-update"),
    path("leases/<int:pk>/activate/", views.LeaseActivateView.as_view(), name="lease-activate"),
    path("leases/<int:pk>/end/", views.LeaseEndView.as_view(), name="lease-end"),
    path("leases/<int:pk>/delete/", views.LeaseDeleteView.as_view(), name="lease-delete"),
    path("leases/<int:pk>/document/", views.LeaseDocumentView.as_view(), name="lease-document"),
    # E1: the rent schedule and the triple-net amount.
    path(
        "leases/<int:pk>/schedule/generate/",
        views.RentScheduleGenerateView.as_view(),
        name="rent-schedule-generate",
    ),
    path(
        "leases/<int:pk>/rent-periods/<int:period_pk>/edit/",
        views.RentPeriodUpdateView.as_view(),
        name="rent-period-update",
    ),
    path("leases/<int:pk>/nnn/", views.NnnRateStageView.as_view(), name="nnn-stage"),
]
