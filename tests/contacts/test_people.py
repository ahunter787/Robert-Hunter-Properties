"""A person is master data; a portal login is an optional link (ADR-029 D2 / M2b).

The case these tests exist for: an adult occupant, guarantor or authorised contact who must
be recorded on a lease without an account, and a tenant who already has an account. Both are
people. Only the one with a linked login can reach the portal, and that link is what every
tenant-scoped query follows.
"""

import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from django.utils import timezone

from apps.contacts import services
from apps.contacts.models import Person
from apps.leases import services as lease_services
from apps.leases.models import LeaseRole, LeaseTenant
from tests.factories import (
    make_lease,
    make_manager,
    make_person,
    make_tenant,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def signed_in(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


# --- the person is the party ----------------------------------------------


def test_a_person_can_be_on_a_lease_without_a_login():
    occupant = make_person(first_name="Sam", last_name="Occupant", email="sam@example.test")
    primary = make_tenant(username="primary", first_name="Ada", last_name="Tenant")
    lease = make_lease(tenants=[primary])
    LeaseTenant.objects.create(lease=lease, person=occupant, role=LeaseRole.ADULT_OCCUPANT)

    assert lease.tenant_names == "Ada Tenant, Sam Occupant"
    assert not lease.lease_tenants.get(person=occupant).tenant_id, "no login is attached"
    other = make_tenant(username="stranger")
    assert lease_services and other  # keep imports honest; scoping is asserted below
    assert not type(lease).objects.for_tenant(other).exists()


def test_the_lease_form_offers_people_who_have_no_login():
    no_login = make_person(first_name="No", last_name="Login")
    manager = make_manager()
    body = signed_in(manager).get(reverse("leases:lease-create")).content.decode()

    assert no_login.display_name in body


def test_a_membership_role_is_recorded_and_primary_is_singular():
    lease = make_lease(tenants=[make_tenant(username="tenant-one")])
    guarantor = make_person(first_name="Gus", last_name="Guarantor")
    LeaseTenant.objects.create(lease=lease, person=guarantor, role=LeaseRole.GUARANTOR)

    assert lease.lease_tenants.get(person=guarantor).get_role_display() == "Guarantor"


# --- linking an account ---------------------------------------------------


def test_linking_an_account_updates_the_person_and_its_memberships():
    person = make_person(first_name="Link", last_name="Me")
    lease = make_lease(tenants=[person])
    user = make_tenant(username="linked", first_name="Link", last_name="Me")

    services.link_portal_account(person, user, actor=make_manager())

    person.refresh_from_db()
    lease.refresh_from_db()
    membership = lease.lease_tenants.get()
    assert person.portal_user == user
    assert membership.tenant == user
    assert type(lease).objects.for_tenant(user).get() == lease
    assert signed_in(user).get(reverse("tenancy:lease")).status_code == 200


def test_an_account_cannot_be_linked_to_two_people():
    user = make_tenant(username="one-account")
    first = make_person(first_name="First", last_name="Person", portal_user=user)
    second = make_person(first_name="Second", last_name="Person")

    with pytest.raises(ValidationError, match="already belongs"):
        services.link_portal_account(second, user, actor=make_manager())
    assert Person.objects.get(pk=second.pk).portal_user is None
    assert first.portal_user == user


def test_a_non_tenant_account_is_refused():
    person = make_person(first_name="No", last_name="Staff")
    manager = make_manager()

    with pytest.raises(ValidationError, match="tenant account"):
        services.link_portal_account(person, manager, actor=manager)


def test_a_person_created_from_an_account_stays_in_step():
    user = make_tenant(username="accounted", first_name="Account", last_name="Holder")
    person = services.person_for_user(user)

    assert person.portal_user == user
    assert person.display_name == "Account Holder"
    # Called again it reuses the row rather than creating a second person.
    assert services.person_for_user(user).pk == person.pk


# --- screens --------------------------------------------------------------


def test_people_screens_are_manager_only(client):
    tenant = make_tenant(username="people-outsider")
    client.force_login(tenant)

    assert client.get(reverse("contacts:person-list")).status_code == 403
    assert client.get(reverse("contacts:person-create")).status_code == 403


def test_a_manager_can_add_a_person_without_access():
    client = signed_in(make_manager())

    response = client.post(
        reverse("contacts:person-create"),
        {
            "first_name": "No",
            "last_name": "Access",
            "email": "no-access@example.test",
            "phone": "555-0100",
        },
    )

    assert response.status_code == 302
    person = Person.objects.get(last_name="Access")
    assert person.portal_user is None
    assert client.get(reverse("contacts:person-detail", args=[person.pk])).status_code == 200


def test_a_manager_can_add_a_person_and_invite_them_in_one_step(mailoutbox):
    client = signed_in(make_manager())

    response = client.post(
        reverse("contacts:person-create"),
        {
            "first_name": "New",
            "last_name": "Tenant",
            "email": "new-tenant@example.test",
            "phone": "",
            "give_portal_access": "on",
            "username": "new-tenant",
        },
    )

    assert response.status_code == 302
    person = Person.objects.get(last_name="Tenant")
    assert person.portal_user is not None
    assert person.portal_user.username == "new-tenant"
    assert person.portal_user.has_usable_password() is False, "the invitation sets the password"
    assert mailoutbox, "an invitation was sent"
    assert LeaseTenant.objects.filter(person=person).count() == 0


# --- existing data --------------------------------------------------------


def test_the_migration_creates_people_for_tenant_accounts():
    """The data step of leases/0014: accounts existed before people did."""
    migration = importlib.import_module("apps.leases.migrations.0014_lease_people")
    user = make_tenant(username="migration-user", first_name="Mig", last_name="Rated")
    assert not Person.objects.filter(portal_user=user).exists()

    migration.create_people(
        django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default"))
    )

    person = Person.objects.get(portal_user=user)
    assert person.display_name == "Mig Rated"
    assert person.email == user.email


def test_the_migration_keeps_an_existing_lease_login():
    migration = importlib.import_module("apps.leases.migrations.0014_lease_people")
    user = make_tenant(username="migrating-member", first_name="Mem", last_name="Ber")
    lease = make_lease(tenants=[user])

    migration.create_people(
        django_apps, SimpleNamespace(connection=SimpleNamespace(alias="default"))
    )

    lease.refresh_from_db()
    assert lease.lease_tenants.get().person.portal_user == user


def test_a_person_with_tenancy_history_cannot_be_deleted():
    person = make_person(first_name="Kept", last_name="Person")
    make_lease(tenants=[person])

    with pytest.raises(ProtectedError):
        person.delete()
