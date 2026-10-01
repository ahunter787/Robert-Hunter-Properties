"""Role model behaviour: the properties every authorization decision relies on."""

import importlib

import pytest
from django.apps import apps as global_apps

from apps.accounts.models import Role, User
from tests.factories import DEFAULT_PASSWORD, make_tenant

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("role", "is_staff_role", "is_admin"),
    [
        (Role.SUPERADMIN, True, True),
        (Role.ADMIN, True, True),
        (Role.MANAGER, True, False),
        (Role.MAINTENANCE, True, False),
        (Role.TENANT, False, False),
    ],
)
def test_role_properties(role, is_staff_role, is_admin):
    user = User.objects.create_user(username=f"user-{role}", role=role)

    assert user.is_rhp_staff is is_staff_role
    assert user.is_admin_or_above is is_admin
    assert user.is_tenant is (role == Role.TENANT)


def test_superuser_is_staff_and_superadmin_whatever_the_role_says():
    # Defensive: a superuser must never be locked out by a stale role value.
    user = User.objects.create_user(username="odd-superuser", role=Role.TENANT)
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])

    assert user.is_rhp_staff is True
    assert user.is_superadmin is True
    assert user.is_admin_or_above is True
    assert user.is_tenant is False


def test_createsuperuser_assigns_the_superadmin_role():
    user = User.objects.create_superuser(username="new-root", password=DEFAULT_PASSWORD)

    assert user.role == Role.SUPERADMIN


def test_default_role_is_tenant():
    assert User(username="fresh").role == Role.TENANT


def test_display_name_falls_back_to_username():
    assert make_tenant(username="plain").display_name == "plain"
    assert make_tenant(username="named", first_name="Ada", last_name="Lovelace").display_name == (
        "Ada Lovelace"
    )


def test_tenant_profile_is_created_for_tenants():
    tenant = make_tenant(username="with-profile")

    assert tenant.tenant_profile.phone == ""
    assert str(tenant.tenant_profile).startswith("with-profile")


def test_backfill_migration_promotes_existing_superusers():
    """The Phase 1 data migration must not leave a legacy admin without a role."""
    migration = importlib.import_module("apps.accounts.migrations.0003_backfill_superadmin_role")

    legacy = make_tenant(username="legacy-admin")
    legacy.is_superuser = True
    legacy.is_staff = True
    legacy.role = Role.TENANT
    legacy.save(update_fields=["is_superuser", "is_staff", "role"])

    migration.forwards(global_apps, None)
    legacy.refresh_from_db()

    assert legacy.role == Role.SUPERADMIN
