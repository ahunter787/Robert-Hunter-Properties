"""The four Phase 1 acceptance criteria, plus the surrounding role gates.

Specification:
  - a tenant cannot access management routes
  - tenant A cannot access tenant B data
  - a maintenance user has restricted access
  - an admin can administer accounts
"""

import pytest
from django.urls import reverse

from apps.accounts.models import Role, TenantProfile, User
from apps.accounts.permissions import tenant_scope
from tests.factories import (
    DEFAULT_PASSWORD,
    make_admin,
    make_maintenance,
    make_manager,
    make_superadmin,
    make_tenant,
)

pytestmark = pytest.mark.django_db


# --- Criterion 1: a tenant cannot access management routes ----------------


@pytest.mark.parametrize(
    "url_name",
    ["manage:home", "manage:account-list", "manage:account-create"],
)
def test_tenant_is_forbidden_from_management_routes(client, url_name):
    client.force_login(make_tenant(username="tenant-gate"))

    response = client.get(reverse(url_name))

    assert response.status_code == 403
    assert b"403" in response.content


def test_tenant_cannot_open_an_account_detail_page(client):
    tenant = make_tenant(username="tenant-self")
    other = make_tenant(username="tenant-other")
    client.force_login(tenant)

    response = client.get(reverse("manage:account-detail", args=[other.pk]))

    assert response.status_code == 403


def test_anonymous_visitor_is_sent_to_sign_in(client):
    response = client.get(reverse("manage:home"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


# --- Criterion 2: tenant A cannot access tenant B data --------------------


def test_profile_only_ever_shows_the_signed_in_tenant(client):
    mine = make_tenant(username="tenant-a", first_name="Alice", last_name="Adams")
    theirs = make_tenant(username="tenant-b", first_name="Bob", last_name="Brown")
    theirs.tenant_profile.notes = "Bob's confidential staff note"
    theirs.tenant_profile.save()

    client.force_login(mine)
    response = client.get(reverse("accounts:profile"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "tenant-a" in body
    assert "tenant-b" not in body
    assert "confidential staff note" not in body


def test_tenant_scope_limits_querysets_to_the_signed_in_tenant():
    mine = make_tenant(username="scope-a")
    make_tenant(username="scope-b")

    scoped = tenant_scope(mine, TenantProfile.objects.all())

    assert list(scoped.values_list("user__username", flat=True)) == ["scope-a"]


def test_tenant_scope_leaves_staff_querysets_alone():
    make_tenant(username="scope-c")
    make_tenant(username="scope-d")

    scoped = tenant_scope(make_admin(username="scope-admin"), TenantProfile.objects.all())

    assert scoped.count() == 2


def test_tenant_cannot_set_staff_only_notes(client):
    tenant = make_tenant(username="tenant-notes")

    client.force_login(tenant)
    response = client.post(
        reverse("accounts:profile"),
        {"phone": "555-0100", "preferred_contact_method": "phone", "notes": "injected"},
    )

    tenant.tenant_profile.refresh_from_db()
    assert response.status_code == 302
    assert tenant.tenant_profile.phone == "555-0100"
    assert tenant.tenant_profile.notes == ""


# --- Criterion 3: a maintenance user has restricted access ----------------


def test_maintenance_user_reaches_management_but_not_accounts(client):
    client.force_login(make_maintenance(username="maint-gate"))

    assert client.get(reverse("manage:home")).status_code == 200
    assert client.get(reverse("manage:account-list")).status_code == 403
    assert client.get(reverse("manage:account-create")).status_code == 403


def test_manager_cannot_administer_accounts(client):
    """Phase 2 widened *reading* tenant records to managers; changing them did not move."""
    tenant = make_tenant(username="manager-readonly-tenant")
    client.force_login(make_manager(username="manager-gate"))

    assert client.get(reverse("manage:home")).status_code == 200
    assert client.get(reverse("manage:account-create")).status_code == 403
    assert client.post(reverse("manage:account-toggle-active", args=[tenant.pk])).status_code == 403
    assert (
        client.post(
            reverse("manage:account-role", args=[tenant.pk]), {"role": Role.MANAGER}
        ).status_code
        == 403
    )


def test_maintenance_home_hides_tenant_totals(client):
    make_tenant(username="counted-tenant")
    client.force_login(make_maintenance(username="maint-totals"))

    body = client.get(reverse("manage:home")).content.decode()

    assert "Invitations" not in body


# --- Criterion 4: an admin can administer accounts ------------------------


def test_admin_can_list_and_open_accounts(client):
    tenant = make_tenant(username="listed-tenant")
    client.force_login(make_admin(username="admin-list"))

    assert client.get(reverse("manage:account-list")).status_code == 200
    assert client.get(reverse("manage:account-detail", args=[tenant.pk])).status_code == 200


def test_admin_can_create_a_tenant_account(client, mailoutbox):
    client.force_login(make_admin(username="admin-create"))

    response = client.post(
        reverse("manage:account-create"),
        {
            "username": "brand-new",
            "email": "brand-new@example.com",
            "first_name": "New",
            "last_name": "Tenant",
            "phone": "555-0111",
        },
    )

    assert response.status_code == 302
    created = User.objects.get(username="brand-new")
    assert created.role == Role.TENANT
    assert created.has_usable_password() is False
    assert created.tenant_profile.phone == "555-0111"
    assert len(mailoutbox) == 1


def test_admin_can_deactivate_and_reactivate_a_tenant(client):
    tenant = make_tenant(username="toggle-me")
    client.force_login(make_admin(username="admin-toggle"))

    client.post(reverse("manage:account-toggle-active", args=[tenant.pk]))
    tenant.refresh_from_db()
    assert tenant.is_active is False

    client.post(reverse("manage:account-toggle-active", args=[tenant.pk]))
    tenant.refresh_from_db()
    assert tenant.is_active is True


def test_deactivated_tenant_cannot_sign_in(client):
    tenant = make_tenant(username="deactivated")
    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    response = client.post(
        reverse("accounts:login"),
        {"username": "deactivated", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200  # stayed on the form
    assert "_auth_user_id" not in client.session


def test_only_superadmin_can_change_a_role(client):
    tenant = make_tenant(username="role-target")
    admin = make_admin(username="admin-role")
    superadmin = make_superadmin(username="superadmin-role")

    client.force_login(admin)
    response = client.post(reverse("manage:account-role", args=[tenant.pk]), {"role": Role.MANAGER})
    assert response.status_code == 403
    tenant.refresh_from_db()
    assert tenant.role == Role.TENANT

    client.force_login(superadmin)
    response = client.post(reverse("manage:account-role", args=[tenant.pk]), {"role": Role.MANAGER})
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.role == Role.MANAGER


def test_only_superadmin_sees_the_role_control(client):
    tenant = make_tenant(username="role-view-target")

    client.force_login(make_admin(username="admin-role-view"))
    admin_body = client.get(reverse("manage:account-detail", args=[tenant.pk])).content.decode()
    assert "Change role" not in admin_body
    assert "Only a superadmin can change roles." in admin_body

    client.force_login(make_superadmin(username="superadmin-role-view"))
    superadmin_body = client.get(
        reverse("manage:account-detail", args=[tenant.pk])
    ).content.decode()
    assert "Change role" in superadmin_body


# --- Landing behavior ----------------------------------------------------


def test_anonymous_visitor_can_reach_the_sign_in_page(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert b"Sign in" in response.content
