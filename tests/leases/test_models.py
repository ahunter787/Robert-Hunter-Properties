"""Lease model behaviour: the constraints that make the data trustworthy."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.leases.models import Lease, LeaseStatus, LeaseTenant
from tests.factories import make_lease, make_property, make_tenant, make_unit

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


# --- one active lease per unit (the rule that stops double-letting) -------


def test_a_unit_can_only_have_one_active_lease():
    unit = make_unit()
    make_lease(unit)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_lease(unit)


def test_a_unit_can_hold_several_drafts():
    unit = make_unit()
    make_lease(unit, status=LeaseStatus.DRAFT)
    make_lease(unit, status=LeaseStatus.DRAFT)

    assert Lease.objects.filter(unit=unit, status=LeaseStatus.DRAFT).count() == 2


def test_an_ended_lease_does_not_block_a_new_active_one():
    unit = make_unit()
    make_lease(
        unit,
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=40),
    )

    make_lease(unit)

    assert Lease.objects.filter(unit=unit, status=LeaseStatus.ACTIVE).count() == 1


def test_two_units_can_each_have_an_active_lease():
    property_ = make_property()
    first = make_unit(property_, identifier="A")
    second = make_unit(property_, identifier="B")

    make_lease(first)
    make_lease(second)

    assert Lease.objects.active().count() == 2


# --- the term -------------------------------------------------------------


def test_a_lease_cannot_end_before_it_starts():
    unit = make_unit()

    with pytest.raises(IntegrityError), transaction.atomic():
        make_lease(unit, start_date=TODAY, end_date=TODAY - dt.timedelta(days=1))


# --- tenants --------------------------------------------------------------


def test_a_tenant_appears_once_per_lease():
    unit = make_unit()
    tenant = make_tenant(username="lease-tenant")
    lease = make_lease(unit, tenants=[tenant])

    with pytest.raises(IntegrityError), transaction.atomic():
        LeaseTenant.objects.create(lease=lease, tenant=tenant)


def test_only_one_tenant_can_be_primary():
    unit = make_unit()
    lease = make_lease(
        unit, tenants=[make_tenant(username="first"), make_tenant(username="second")]
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        LeaseTenant.objects.create(
            lease=lease, tenant=make_tenant(username="third"), is_primary=True
        )


def test_tenants_are_listed_with_the_primary_first():
    unit = make_unit()
    ada = make_tenant(username="ada", first_name="Ada", last_name="One")
    ben = make_tenant(username="ben", first_name="Ben", last_name="Two")
    lease = make_lease(unit, tenants=[ada, ben])

    assert [tenant.username for tenant in lease.tenants] == ["ada", "ben"]
    assert lease.primary_tenant == ada
    assert lease.tenant_names == "Ada One, Ben Two"


def test_a_lease_without_tenants_says_so():
    lease = make_lease(make_unit(), status=LeaseStatus.DRAFT)

    assert lease.tenants == []
    assert lease.primary_tenant is None
    assert lease.tenant_names == "No tenants yet"


# --- querysets and the occupancy definition ------------------------------


def test_current_means_active_and_inside_the_term():
    unit = make_unit()
    make_lease(unit, status=LeaseStatus.DRAFT)
    assert not Lease.objects.current()

    lease = Lease.objects.get(status=LeaseStatus.DRAFT)
    lease.status = LeaseStatus.ACTIVE
    lease.save(update_fields=["status"])

    assert list(Lease.objects.current()) == [lease]


def test_a_lease_that_has_not_started_is_not_current():
    unit = make_unit()
    make_lease(
        unit,
        start_date=TODAY + dt.timedelta(days=10),
        end_date=TODAY + dt.timedelta(days=370),
    )

    assert Lease.objects.current().count() == 0
    assert Lease.objects.active().count() == 1


def test_a_lease_whose_term_has_passed_is_not_current():
    unit = make_unit()
    lease = make_lease(
        unit,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    lease.status = LeaseStatus.ACTIVE
    lease.save(update_fields=["status"])

    assert Lease.objects.current().count() == 0


def test_expiring_within_finds_leases_ending_soon():
    soon = make_unit(identifier="Soon")
    later = make_unit(identifier="Later")
    make_lease(soon, end_date=TODAY + dt.timedelta(days=10))
    make_lease(later, end_date=TODAY + dt.timedelta(days=200))

    identifiers = Lease.objects.expiring_within(30).values_list("unit__identifier", flat=True)
    assert list(identifiers) == ["Soon"]


def test_for_tenant_scopes_to_that_person():
    mine = make_lease(make_unit(), tenants=[make_tenant(username="mine")])
    make_lease(make_unit(), tenants=[make_tenant(username="theirs")])

    leases = Lease.objects.for_tenant(mine.tenants[0])

    assert list(leases) == [mine]


def test_due_day_label_reads_naturally():
    assert make_lease(make_unit(), rent_due_day=1).due_day_label == "1st of every month"
    assert make_lease(make_unit(), rent_due_day=2).due_day_label == "2nd of every month"
    assert make_lease(make_unit(), rent_due_day=3).due_day_label == "3rd of every month"
    assert make_lease(make_unit(), rent_due_day=22).due_day_label == "22nd of every month"
    assert make_lease(make_unit(), rent_due_day=31).due_day_label == "31st of every month"


# --- occupancy, as seen from the portfolio --------------------------------


def test_a_unit_with_a_current_lease_is_occupied_by_its_tenants():
    property_ = make_property()
    unit = make_unit(property_, identifier="A")
    tenant = make_tenant(username="occupant", first_name="Occ", last_name="Upant")
    make_lease(unit, tenants=[tenant])

    unit.refresh_from_db()
    assert unit.is_vacant is False
    assert [person.username for person in unit.occupants] == ["occupant"]


def test_a_unit_with_only_a_draft_is_vacant():
    unit = make_unit()
    make_lease(unit, status=LeaseStatus.DRAFT)

    assert unit.is_vacant is True
    assert unit.occupants == []


def test_an_out_of_service_unit_is_neither_vacant_nor_occupied():
    """A retired unit is a third state, not a vacancy.

    Retiring a unit does not end the tenancy in the records (see the next test),
    but a unit that cannot be let must not be counted as vacant either.
    """
    unit = make_unit(is_active=False)
    make_lease(unit)

    assert unit.is_vacant is False
    assert unit.is_occupied is False
    assert unit.current_lease is not None


def test_a_lease_on_a_unit_out_of_service_is_still_current():
    """Retiring a unit does not silently end the tenancy in the records."""
    unit = make_unit(is_active=False)
    lease = make_lease(unit)

    assert lease.is_current is True
    assert lease.is_editable is True


# --- status helpers -------------------------------------------------------


def test_ended_leases_are_history_and_not_editable():
    lease = make_lease(make_unit(), status=LeaseStatus.ENDED)

    assert lease.is_editable is False


def test_draft_leases_are_editable():
    assert make_lease(make_unit(), status=LeaseStatus.DRAFT).is_editable is True


def test_deleting_a_unit_with_a_lease_is_refused():
    unit = make_unit()
    make_lease(unit)

    from django.db.models.deletion import ProtectedError

    with pytest.raises(ProtectedError):
        unit.delete()
