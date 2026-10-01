"""Invitations: creation, single use, deactivation, and the resend path."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounts import emails
from apps.accounts.models import Role, TenantProfile, User
from tests.factories import (
    DEFAULT_PASSWORD,
    invitation_path_from_email,
    make_admin,
    make_invited_tenant,
    make_tenant,
)

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "invited-password-88"


def invite_a_tenant(client, mailoutbox, username="invitee", email="invitee@example.com"):
    client.force_login(make_admin(username="inviting-admin"))
    client.post(
        reverse("manage:account-create"),
        {
            "username": username,
            "email": email,
            "first_name": "In",
            "last_name": "Vitee",
            "phone": "",
        },
    )
    return User.objects.get(username=username), invitation_path_from_email(mailoutbox[-1].body)


def test_invitation_email_contains_a_one_time_link(client, mailoutbox):
    user, link_path = invite_a_tenant(client, mailoutbox)

    assert user.has_usable_password() is False
    assert "/account/invite/" in link_path
    assert "Your RHP portal invitation" in mailoutbox[-1].subject


def test_accepting_an_invitation_sets_the_password_and_signs_in(client, mailoutbox):
    user, link_path = invite_a_tenant(client, mailoutbox)
    client.logout()

    assert client.get(link_path).status_code == 200
    response = client.post(
        link_path, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.has_usable_password() is True
    assert user.check_password(NEW_PASSWORD)
    assert "_auth_user_id" in client.session


def test_invitation_link_is_single_use(client, mailoutbox):
    user, link_path = invite_a_tenant(client, mailoutbox)
    client.logout()
    client.post(link_path, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})

    client.logout()
    response = client.get(link_path)

    assert response.status_code == 400
    assert b"no longer works" in response.content


def test_invitation_link_is_refused_once_the_account_is_deactivated(client, mailoutbox):
    user, link_path = invite_a_tenant(client, mailoutbox)
    client.logout()
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = client.get(link_path)

    assert response.status_code == 400


def test_invitation_token_cannot_be_used_as_a_password_reset_token(client, mailoutbox):
    """Distinct key salts: one flow's token must never work in the other."""
    user, link_path = invite_a_tenant(client, mailoutbox)
    client.logout()

    token = link_path.rstrip("/").split("/")[-1]
    uidb64 = link_path.rstrip("/").split("/")[-2]
    reset_path = reverse(
        "accounts:password-reset-confirm", kwargs={"uidb64": uidb64, "token": token}
    )

    response = client.get(reset_path, follow=True)

    assert b"no longer works" in response.content


def test_unknown_uid_or_token_is_refused(client):
    response = client.get("/account/invite/not-a-uid/not-a-token/")

    assert response.status_code == 400


def test_resending_an_invitation_sends_a_fresh_link(client, mailoutbox):
    user, _ = invite_a_tenant(client, mailoutbox)
    emails_before = len(mailoutbox)

    response = client.post(reverse("manage:account-resend-invite", args=[user.pk]))

    assert response.status_code == 302
    assert len(mailoutbox) == emails_before + 1
    assert "/account/invite/" in mailoutbox[-1].body


def test_resend_is_refused_after_the_password_is_set(client, mailoutbox):
    tenant = make_tenant(username="already-accepted", email="accepted@example.com")
    client.force_login(make_admin(username="resending-admin"))
    emails_before = len(mailoutbox)

    response = client.post(reverse("manage:account-resend-invite", args=[tenant.pk]), follow=True)

    assert len(mailoutbox) == emails_before
    assert b"already set a password" in response.content


def test_create_tenant_command_creates_an_invited_account(mailoutbox):
    call_command("create_tenant", "cli-tenant", "--email", "cli@example.com", "--phone", "555-0123")

    user = User.objects.get(username="cli-tenant")
    assert user.role == Role.TENANT
    assert user.has_usable_password() is False
    assert user.tenant_profile.phone == "555-0123"
    assert len(mailoutbox) == 1


def test_create_tenant_command_can_skip_the_email(mailoutbox):
    call_command("create_tenant", "quiet-tenant", "--email", "quiet@example.com", "--no-email")

    assert User.objects.filter(username="quiet-tenant").exists()
    assert mailoutbox == []


def test_create_tenant_command_refuses_a_duplicate(mailoutbox):
    make_tenant(username="duplicate")

    with pytest.raises(Exception) as error:
        call_command("create_tenant", "duplicate", "--email", "dup@example.com")

    assert "already exists" in str(error.value)


def test_console_backend_is_reported_as_undelivered(settings, mailoutbox):
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.console.EmailBackend",
            "OPTIONS": {},
        }
    }
    user = make_invited_tenant(username="console-invitee")

    assert emails.is_console_backend() is True
    assert emails.send_invitation(user, "http://localhost:8000") is False


def test_deactivated_tenant_cannot_sign_in_even_with_a_password(client):
    tenant = make_tenant(username="inactive-with-password", email="inactive@example.com")
    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    response = client.post(
        reverse("accounts:login"),
        {"username": "inactive-with-password", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert TenantProfile.objects.filter(user=tenant).exists()
