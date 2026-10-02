"""Management-portal URLs.

Everything here is gated by a staff mixin in the view itself; the namespace keeps
staff routes structurally separate from the tenant-facing ones (ADR-003).
"""

from django.urls import path

from apps.accounts import views

app_name = "manage"

urlpatterns = [
    path("", views.ManageHomeView.as_view(), name="home"),
    # Accounts
    path("accounts/", views.TenantAccountListView.as_view(), name="account-list"),
    path("accounts/new/", views.TenantAccountCreateView.as_view(), name="account-create"),
    path("accounts/<int:pk>/", views.TenantAccountDetailView.as_view(), name="account-detail"),
    path(
        "accounts/<int:pk>/toggle-active/",
        views.TenantAccountToggleActiveView.as_view(),
        name="account-toggle-active",
    ),
    path(
        "accounts/<int:pk>/resend-invite/",
        views.TenantAccountResendInviteView.as_view(),
        name="account-resend-invite",
    ),
    path(
        "accounts/<int:pk>/photo/",
        views.TenantPhotoView.as_view(),
        name="account-photo",
    ),
    path(
        "accounts/<int:pk>/photo/set/",
        views.TenantAccountPhotoUpdateView.as_view(),
        name="account-photo-update",
    ),
    path(
        "accounts/<int:pk>/role/",
        views.TenantRoleChangeView.as_view(),
        name="account-role",
    ),
]
