"""Account URLs: sign-in, self-service, and invitations.

Namespaced as ``accounts`` so ``LOGIN_REDIRECT_URL`` can point at the role-aware
landing view by name.
"""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from apps.accounts import views
from apps.accounts.forms import InvitationPasswordForm

app_name = "accounts"

urlpatterns = [
    # Role-aware home: the tenant dashboard, or the management area for staff.
    path("", views.TenantDashboardView.as_view(), name="home"),
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    # The tenant's own photo: no id in the URL by design.
    path("photo/", views.OwnPhotoView.as_view(), name="photo"),
    path(
        "password/",
        auth_views.PasswordChangeView.as_view(
            template_name="account/password_change.html",
            success_url=reverse_lazy("accounts:password-change-done"),
        ),
        name="password-change",
    ),
    path(
        "password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="account/password_change_done.html"
        ),
        name="password-change-done",
    ),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="account/password_reset.html",
            email_template_name="account/email/password_reset_body.txt",
            subject_template_name="account/email/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password-reset-done"),
        ),
        name="password-reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="account/password_reset_done.html"),
        name="password-reset-done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password_reset_confirm.html",
            form_class=InvitationPasswordForm,
            success_url=reverse_lazy("accounts:password-reset-complete"),
        ),
        name="password-reset-confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="account/password_reset_complete.html"
        ),
        name="password-reset-complete",
    ),
    path("invite/<uidb64>/<token>/", views.InvitationAcceptView.as_view(), name="invite"),
]
