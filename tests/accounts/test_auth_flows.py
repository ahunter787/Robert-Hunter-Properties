"""Sign-in, sign-out, and the failure messages they produce."""

import pytest
from django.urls import reverse

from apps.accounts.models import LoginAttempt, Role
from tests.factories import DEFAULT_PASSWORD, make_admin, make_tenant

pytestmark = pytest.mark.django_db


def test_sign_in_page_renders(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert b"Forgot your password?" in response.content


def test_tenant_signs_in_and_lands_on_the_account_page(client):
    make_tenant(username="tenant-login")

    response = client.post(
        reverse("accounts:login"),
        {"username": "tenant-login", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("accounts:home")
    assert client.get(reverse("accounts:home"))["Location"] == reverse("accounts:profile")


def test_staff_signs_in_and_lands_on_the_management_area(client):
    make_admin(username="admin-login")

    response = client.post(
        reverse("accounts:login"),
        {"username": "admin-login", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 302
    assert client.get(reverse("accounts:home"))["Location"] == reverse("manage:home")


def test_bad_password_is_rejected_with_a_generic_message(client):
    make_tenant(username="tenant-bad-pass")

    response = client.post(
        reverse("accounts:login"),
        {"username": "tenant-bad-pass", "password": "not-the-password"},
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert "correct username and password" in body
    assert "_auth_user_id" not in client.session


def test_unknown_account_gets_the_same_message_as_a_bad_password(client):
    make_tenant(username="tenant-known")

    known = client.post(
        reverse("accounts:login"),
        {"username": "tenant-known", "password": "wrong"},
    ).content.decode()
    unknown = client.post(
        reverse("accounts:login"),
        {"username": "does-not-exist", "password": "wrong"},
    ).content.decode()

    assert "correct username and password" in known
    assert "correct username and password" in unknown


def test_successful_sign_in_clears_earlier_failures(client):
    tenant = make_tenant(username="tenant-clears")
    LoginAttempt.objects.create(username="tenant-clears", successful=False)

    client.post(
        reverse("accounts:login"),
        {"username": "tenant-clears", "password": DEFAULT_PASSWORD},
    )

    assert LoginAttempt.objects.filter(username="tenant-clears", successful=False).count() == 0
    assert LoginAttempt.objects.filter(username="tenant-clears", successful=True).count() == 1
    assert tenant.pk is not None


def test_authenticated_user_visiting_login_is_redirected(client):
    tenant = make_tenant(username="tenant-already-in")
    client.force_login(tenant)

    response = client.get(reverse("accounts:login"))

    assert response.status_code == 302


def test_sign_out_requires_post(client):
    tenant = make_tenant(username="tenant-logout")
    client.force_login(tenant)

    assert client.get(reverse("accounts:logout")).status_code == 405

    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_role_display_names_come_from_the_model(client):
    tenant = make_tenant(username="tenant-role-label")
    client.force_login(tenant)

    body = client.get(reverse("accounts:profile")).content.decode()

    assert Role.TENANT.label in body
