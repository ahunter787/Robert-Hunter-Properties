"""Responsibility URLs, mounted under ``/manage/``.

Namespaced ``responsibilities``: a property's bills are edited from the property
screen, and the ledger points back to them rather than growing its own copy.
"""

from django.urls import path

from apps.responsibilities import views

app_name = "responsibilities"

urlpatterns = [
    path(
        "properties/<int:pk>/responsibilities/new/",
        views.ResponsibilityCreateView.as_view(),
        name="responsibility-create",
    ),
    path(
        "responsibilities/<int:pk>/edit/",
        views.ResponsibilityUpdateView.as_view(),
        name="responsibility-update",
    ),
    path(
        "responsibilities/<int:pk>/cycles/new/",
        views.CycleStageView.as_view(),
        name="cycle-stage",
    ),
    path(
        "responsibilities/cycles/<int:pk>/shares/",
        views.CycleSharesView.as_view(),
        name="cycle-shares",
    ),
]
