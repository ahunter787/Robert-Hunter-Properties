"""The account page: tenant contact details and the password-change flow."""

import pytest
from django.urls import reverse

from tests.factories import DEFAULT_PASSWORD, make_admin, make_tenant

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "harbour-lantern-52"


def test_tenant_sees_an_editable_profile(client):
    tenant = make_tenant(username="profile-tenant", first_name="Pat", last_name="Tenant")
    client.force_login(tenant)

    body = client.get(reverse("accounts:profile")).content.decode()

    assert "Contact details" in body
    assert "profile-tenant" in body
    assert "Pat Tenant" in body


def test_tenant_can_update_contact_details(client):
    tenant = make_tenant(username="updating-tenant")
    client.force_login(tenant)

    response = client.post(
        reverse("accounts:profile"),
        {"phone": "555-0456", "preferred_contact_method": "text"},
    )

    assert response.status_code == 302
    tenant.tenant_profile.refresh_from_db()
    assert tenant.tenant_profile.phone == "555-0456"
    assert tenant.tenant_profile.preferred_contact_method == "text"


def test_invalid_contact_details_are_rejected(client):
    tenant = make_tenant(username="invalid-contact")
    client.force_login(tenant)

    response = client.post(
        reverse("accounts:profile"),
        {"phone": "x" * 100, "preferred_contact_method": "carrier-pigeon"},
    )

    assert response.status_code == 200
    tenant.tenant_profile.refresh_from_db()
    assert tenant.tenant_profile.phone == ""


def test_staff_profile_has_no_tenant_contact_form(client):
    client.force_login(make_admin(username="staff-profile"))

    body = client.get(reverse("accounts:profile")).content.decode()

    assert "Staff account" in body
    # No tenant contact form is rendered for staff accounts.
    assert 'name="phone"' not in body
    assert 'name="preferred_contact_method"' not in body


def test_staff_cannot_post_tenant_contact_details(client):
    client.force_login(make_admin(username="staff-posting"))

    response = client.post(reverse("accounts:profile"), {"phone": "555-0000"})

    assert response.status_code == 403


def test_password_change_updates_the_credential(client):
    # The new password deliberately shares nothing with the username: Django's
    # similarity validator would (correctly) reject a password like the username.
    tenant = make_tenant(username="quiet-user")
    client.force_login(tenant)

    response = client.post(
        reverse("accounts:password-change"),
        {
            "old_password": DEFAULT_PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("accounts:password-change-done")
    client.logout()
    assert client.login(username="quiet-user", password=NEW_PASSWORD)


def test_password_change_rejects_a_password_too_similar_to_the_username(client):
    # Django's similarity validator compares the whole password against the
    # username, so only a genuinely similar value is rejected.
    tenant = make_tenant(username="quiet-user")
    client.force_login(tenant)

    response = client.post(
        reverse("accounts:password-change"),
        {
            "old_password": DEFAULT_PASSWORD,
            "new_password1": "quiet-user",
            "new_password2": "quiet-user",
        },
    )

    assert response.status_code == 200
    assert b"too similar to the username" in response.content
    tenant.refresh_from_db()
    assert tenant.check_password(DEFAULT_PASSWORD)


def test_password_change_requires_the_current_password(client):
    tenant = make_tenant(username="wrong-old-password")
    client.force_login(tenant)

    response = client.post(
        reverse("accounts:password-change"),
        {
            "old_password": "not-the-current-one",
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.check_password(DEFAULT_PASSWORD)


def test_anonymous_visitor_cannot_open_the_profile(client):
    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
