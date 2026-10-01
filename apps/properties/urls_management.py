"""Portfolio management URLs, mounted under ``/manage/``.

Namespaced ``portfolio`` rather than reusing ``manage``: two ``include()`` calls
sharing one namespace would leave the earlier set of routes unreachable through
``reverse()``.
"""

from django.urls import path

from apps.properties import views

app_name = "portfolio"

urlpatterns = [
    # Properties
    path("properties/", views.PropertyListView.as_view(), name="property-list"),
    path("properties/new/", views.PropertyCreateView.as_view(), name="property-create"),
    path("properties/<int:pk>/", views.PropertyDetailView.as_view(), name="property-detail"),
    path(
        "properties/<int:pk>/banner/",
        views.PropertyBannerView.as_view(),
        name="property-banner",
    ),
    path("properties/<int:pk>/edit/", views.PropertyUpdateView.as_view(), name="property-update"),
    path(
        "properties/<int:pk>/toggle-active/",
        views.PropertyToggleActiveView.as_view(),
        name="property-toggle-active",
    ),
    path("properties/<int:pk>/delete/", views.PropertyDeleteView.as_view(), name="property-delete"),
    # Units
    path("units/", views.UnitListView.as_view(), name="unit-list"),
    path("units/new/", views.UnitCreateView.as_view(), name="unit-create"),
    path("units/<int:pk>/", views.UnitDetailView.as_view(), name="unit-detail"),
    path("units/<int:pk>/edit/", views.UnitUpdateView.as_view(), name="unit-update"),
    path(
        "units/<int:pk>/toggle-active/",
        views.UnitToggleActiveView.as_view(),
        name="unit-toggle-active",
    ),
    path("units/<int:pk>/delete/", views.UnitDeleteView.as_view(), name="unit-delete"),
]
