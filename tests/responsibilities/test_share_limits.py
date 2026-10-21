"""The units divide the bill, and never more than it (E2, ADR-014).

The owner found this by trying it: on the screen that divides a $700 quarterly water bill
(233.33 a month), the form accepted 100 for one unit and 600 for the other — 700 a month
against a bill of 233.33 — and saved it. Nothing checked, so nothing objected, and the tenants
would have been billed three times what the property cost.

The bill is the ceiling. What the units carry may be *less* than it, because a vacant unit's
share stays with the owner, and the screen says how much is left. Two screens can set the
amounts — staging a bill and changing the amounts afterwards — so both are held to it, here
and in the service where the shares are written.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ledger import services as ledger_services
from apps.responsibilities import services as responsibility_services
from tests.factories import (
    make_admin,
    make_cycle,
    make_lease,
    make_manager,
    make_property,
    make_responsibility,
    make_share,
    make_unit,
)
from tests.responsibilities.helpers import allocation_page, new_bill_page, payload, reviewed_save

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="share-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="share-manager"))
    return client


@pytest.fixture
def water_bill():
    """910 Stark's shape: two sized units and a $700 quarterly bill, 233.33 a month."""
    property_obj = make_property(name="Water Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=1450)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=2000)
    responsibility = make_responsibility(property_obj, label="Water", cycle_months=3)
    cycle = make_cycle(
        responsibility,
        starts_on=TODAY.replace(day=1),
        months=3,
        total_amount=Decimal("700.00"),
    )
    return property_obj, first, second, responsibility, cycle


def shares_of(cycle) -> dict[int, Decimal]:
    return {share.unit_id: share.monthly_amount for share in cycle.shares.all()}


# --- what the bill divides, and what the proposals do with it --------------


def test_the_proposals_divide_the_bill_exactly(water_bill):
    _property, first, second, _responsibility, cycle = water_bill

    proposals = responsibility_services.propose_shares(cycle)

    assert cycle.monthly_total == Decimal("233.33")
    assert sum(proposals.values()) == Decimal("233.33"), "no penny left floating"
    assert proposals[first.pk] == Decimal("98.07"), "42.03% by area"
    assert proposals[second.pk] == Decimal("135.26")


def test_proposals_absorb_rounding_so_they_still_add_up():
    """Three equal units of 100.00 do not divide evenly, and the largest carries the cent."""
    property_obj = make_property(name="Thirds Building")
    units = [
        make_unit(for_property=property_obj, identifier=str(number), square_feet=100)
        for number in (1, 2, 3)
    ]
    responsibility = make_responsibility(property_obj, label="Trash", cycle_months=3)
    cycle = make_cycle(
        responsibility,
        starts_on=TODAY.replace(day=1),
        months=3,
        total_amount=Decimal("100.00"),
    )

    proposals = responsibility_services.propose_shares(cycle)

    assert sum(proposals.values()) == cycle.monthly_total == Decimal("33.33")
    assert set(proposals) == {unit.pk for unit in units}


# --- the ceiling -----------------------------------------------------------


def test_the_shares_screen_refuses_more_than_the_bill(as_manager, water_bill):
    _property, first, second, _responsibility, cycle = water_bill
    page = allocation_page(as_manager, cycle)
    response = as_manager.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]),
        payload(page, action="review", **{f"unit_{first.pk}": "100", f"unit_{second.pk}": "600"}),
    )
    assert response.status_code == 200
    assert b"exceed the monthly bill by $466.67" in response.content
    assert not cycle.shares.exists()


def test_the_shares_screen_allows_less_and_says_what_is_left(as_admin, water_bill):
    _property, first, second, _responsibility, cycle = water_bill
    page = allocation_page(as_admin, cycle)
    response = as_admin.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]),
        payload(page, action="review", **{f"unit_{first.pk}": "100", f"unit_{second.pk}": "0"}),
    )
    assert response.context["step"] == "review"
    assert response.context["worksheet"].left == Decimal("133.33")
    saved = as_admin.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]), payload(response, action="save")
    )
    assert saved.status_code == 302
    assert shares_of(cycle) == {first.pk: Decimal("100.00")}


def test_staging_a_bill_is_held_to_the_same_ceiling(as_admin, water_bill):
    _property, first, second, responsibility, _cycle = water_bill
    page = new_bill_page(
        as_admin,
        responsibility,
        starts_on=TODAY.replace(day=1) + dt.timedelta(days=200),
        months=3,
        total_amount="700",
    )
    response = as_admin.post(
        reverse("responsibilities:cycle-stage", args=[responsibility.pk]),
        payload(page, action="review", **{f"unit_{first.pk}": "100", f"unit_{second.pk}": "600"}),
    )
    assert b"exceed the monthly bill by $466.67" in response.content
    assert responsibility.cycles.count() == 1


def test_the_service_refuses_the_ceiling_whatever_the_screen_did(water_bill):
    """The screen is not the only caller, so the rule lives where the shares are written."""
    _property, first, second, _responsibility, cycle = water_bill

    with pytest.raises(Exception) as raised:
        responsibility_services.set_shares(
            cycle, {first.pk: Decimal("100.00"), second.pk: Decimal("600.00")}
        )

    assert "add up to 700.00 a month" in str(raised.value)
    assert not cycle.shares.exists()


# --- blank means the share the screen promises -----------------------------


def test_blank_fields_require_explicit_allocation(as_admin, water_bill):
    _property, first, second, _responsibility, cycle = water_bill
    make_share(cycle, first, monthly_amount=Decimal("60"))
    make_share(cycle, second, monthly_amount=Decimal("140"))
    page = allocation_page(as_admin, cycle)
    response = as_admin.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]),
        payload(page, action="review", **{f"unit_{first.pk}": "", f"unit_{second.pk}": ""}),
    )
    assert response.context["allocation"].errors
    assert shares_of(cycle) == {first.pk: Decimal("60"), second.pk: Decimal("140")}


def test_a_zero_takes_a_unit_out_of_the_bill(as_admin, water_bill):
    _property, first, second, _responsibility, cycle = water_bill
    make_share(cycle, first, monthly_amount=Decimal("98.07"))
    make_share(cycle, second, monthly_amount=Decimal("135.26"))
    response = reviewed_save(as_admin, cycle, **{f"unit_{first.pk}": "0.00"})
    assert response.status_code == 302
    assert shares_of(cycle) == {second.pk: Decimal("135.26")}


# --- posting what the shares produce ---------------------------------------


def test_the_balances_screen_offers_to_post_due_charges(as_admin, water_bill):
    """The owner saw "not posted" there and no way to act on it."""
    _property, first, _second, _responsibility, cycle = water_bill
    make_share(cycle, first, monthly_amount=Decimal("98.07"))
    lease = make_lease(
        first,
        start_date=TODAY.replace(day=1),
        end_date=TODAY + dt.timedelta(days=300),
        rent_due_day=1,
        monthly_rent=Decimal("1000.00"),
    )

    body = " ".join(as_admin.get(reverse("ledger:overview")).content.decode().split())
    assert "Post due charges" in body
    assert "Due now and not posted — rent, NNN and expense recoveries." in body

    as_admin.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    charged = lease.charges.filter(kind="RESPONSIBILITY")
    assert charged.count() == 1, "the water share was posted from the balances screen"
    assert charged.get().amount == Decimal("98.07")


def test_a_tenancy_with_nothing_due_is_not_offered_the_button(as_admin, water_bill):
    _property, first, _second, _responsibility, _cycle = water_bill
    lease = make_lease(
        first,
        start_date=TODAY - dt.timedelta(days=200),
        end_date=TODAY - dt.timedelta(days=10),
        monthly_rent=Decimal("1000.00"),
    )
    ledger_services.generate_charges(lease, through=lease.end_date)

    body = " ".join(as_admin.get(reverse("ledger:overview")).content.decode().split())

    assert "Due now and not posted" not in body


# --- the wall the owner hit: nothing can be posted until the tenancy is placed ------------


def test_a_tenancy_waiting_to_be_set_up_is_told_so_wherever_it_is_read(as_admin, water_bill):
    """A tenancy that began before RHP cannot be billed until its history is entered (E4).

    Both screens used to stay silent: the ledger simply had no button and the balances list
    said nothing, which is the dead end the owner found.
    """
    _property, first, _second, _responsibility, cycle = water_bill
    make_share(cycle, first, monthly_amount=Decimal("98.07"))
    lease = make_lease(
        first,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY + dt.timedelta(days=60),
        rent_due_day=1,
        monthly_rent=Decimal("1000.00"),
        billing_start_date=None,
    )

    ledger_page = " ".join(
        as_admin.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode().split()
    )
    overview = " ".join(as_admin.get(reverse("ledger:overview")).content.decode().split())
    lease_list = " ".join(as_admin.get(reverse("leases:lease-list")).content.decode().split())
    setup_url = reverse("leases:onboard", args=[lease.pk])

    assert "Set the starting account balance before posting charges." in ledger_page
    assert setup_url in ledger_page
    assert "Post due charges" not in ledger_page
    assert "Starting account balance has not been recorded" in overview
    assert setup_url in overview
    assert "Needs setup" in lease_list


def test_setting_up_the_prior_activity_opens_posting(as_admin, water_bill):
    """The answer to "how do I post them?" — place the tenancy, then post."""
    _property, first, _second, responsibility, cycle = water_bill
    del responsibility
    make_share(cycle, first, monthly_amount=Decimal("98.07"))
    lease = make_lease(
        first,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY + dt.timedelta(days=60),
        rent_due_day=1,
        monthly_rent=Decimal("1000.00"),
        billing_start_date=None,
    )
    assert lease.needs_onboarding is True

    onboarding_services = __import__(
        "apps.leases.services", fromlist=["onboard_lease"]
    ).onboard_lease(
        lease,
        method="POSITION",
        as_of=TODAY,
        opening_amount=Decimal("0.00"),
        billing_start_date=TODAY.replace(day=1),
    )

    lease.refresh_from_db()
    assert onboarding_services is not None
    assert lease.needs_onboarding is False

    body = " ".join(
        as_admin.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode().split()
    )
    assert "Post due charges" in body

    as_admin.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    assert lease.charges.filter(kind="RESPONSIBILITY").count() == 1
    assert lease.charges.get(kind="RESPONSIBILITY").amount == Decimal("98.07")
