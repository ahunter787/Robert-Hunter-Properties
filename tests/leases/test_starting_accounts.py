"""Starting accounts place a pre-RHP tenancy, and a stated schedule is the office's.

The failing case: a lease that began years ago, activated and charged the ordinary way,
produced 108 charges and a $100,536 "balance" for a tenant who was paid up. One gate makes
that impossible; the reviewed starting account (ADR-027) places the tenancy; and a stated
schedule lets the office record the amounts the paper actually names. The E4 HISTORY /
POSITION mechanism is retired (ADR-028 D2) — these tests cover what remains.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.leases import services as lease_services
from apps.leases.models import LeaseTemplate, RentPeriodOrigin
from apps.ledger import services as ledger_services
from tests.factories import (
    make_admin,
    make_lease,
    make_manager,
    make_tenant,
    place_lease,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()

#: Michael Ortolano's live lease shape: six stated amounts, NNN adjusted each October.
MICHAEL_SCHEDULE = [
    (dt.date(2022, 6, 1), "1450.00"),
    (dt.date(2023, 6, 1), "1508.00"),
    (dt.date(2023, 11, 1), "1852.00"),  # Extra Space, mid-year
    (dt.date(2024, 6, 1), "1925.00"),
    (dt.date(2025, 6, 1), "2002.00"),
    (dt.date(2026, 6, 1), "2113.00"),
]


def a_live_tenancy(**fields):
    """A tenancy that began years ago and has not been placed in RHP yet."""
    fields.setdefault("start_date", dt.date(2022, 6, 1))
    fields.setdefault("end_date", dt.date(2027, 5, 30))
    fields.setdefault("monthly_rent", Decimal("1450.00"))
    fields.setdefault("rent_due_day", 1)
    fields.setdefault("template", LeaseTemplate.NNN)
    fields.setdefault("step_up_month", None)
    fields.setdefault("billing_start_date", None)
    return make_lease(**fields)


# --- the one placement gate ------------------------------------------------


def test_a_tenancy_from_before_rhp_cannot_be_charged_yet():
    lease = a_live_tenancy()

    assert lease.needs_starting_account is True

    with pytest.raises(ValidationError, match="Record its starting account balance"):
        ledger_services.generate_charges(lease, through=TODAY)

    assert not lease.charges.exists(), "nothing was posted"


def test_a_tenancy_that_began_this_month_is_charged_as_always():
    lease = make_lease(start_date=TODAY.replace(day=1), rent_due_day=1)
    del lease.billing_start_date  # the factory marks it placed; this one never needed placing

    assert lease.needs_starting_account is False
    ledger_services.generate_charges(lease, through=TODAY)
    assert lease.charges.count() == 1


def test_a_manual_charge_cannot_bypass_the_starting_account():
    lease = a_live_tenancy()

    with pytest.raises(ValidationError, match="Record its starting account balance"):
        ledger_services.create_charge(
            lease, description="Key replacement", amount=Decimal("25.00"), due_date=TODAY
        )
    assert not lease.charges.exists()


def test_the_cutover_is_what_unlocks_charging():
    lease = a_live_tenancy(billing_start_date=dt.date(2026, 1, 1))

    ledger_services.generate_charges(lease, through=dt.date(2026, 2, 28))

    assert [c.due_date for c in lease.charges.order_by("due_date")] == [
        dt.date(2026, 1, 1),
        dt.date(2026, 2, 1),
    ], "billed from the cutover, not from the term's start"


# --- a stated schedule the office owns ------------------------------------


def test_a_stated_lease_keeps_the_amounts_the_office_entered():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=dt.date(2022, 6, 1))
    for effective_from, amount in MICHAEL_SCHEDULE:
        lease_services.add_rent_period(lease, effective_from=effective_from, amount=Decimal(amount))

    result = lease_services.generate_rent_schedule(lease)

    assert result.created == [] and result.removed == []
    assert lease.rent_periods.count() == len(MICHAEL_SCHEDULE)
    assert lease.rent_for(dt.date(2023, 11, 1)) == Decimal("1852.00")


def test_a_hand_set_period_survives_regenerating_a_stepped_schedule():
    """The defect E4 fixed: a rule cannot plan a mid-year change, so it must not delete it."""
    lease = make_lease(
        start_date=dt.date(2027, 1, 1),
        end_date=dt.date(2030, 12, 31),
        rent_due_day=5,
        template=LeaseTemplate.STEP_UP,
        step_up_month=6,
        step_up_percent=Decimal("4.00"),
    )
    lease_services.generate_rent_schedule(lease)
    extra = lease_services.add_rent_period(
        lease,
        effective_from=dt.date(2027, 11, 5),
        amount=Decimal("1852.00"),
        note="Extra space taken",
    )

    result = lease_services.generate_rent_schedule(lease)

    extra.refresh_from_db()
    assert extra.amount == Decimal("1852.00")
    assert extra.origin == RentPeriodOrigin.MANUAL
    assert dt.date(2027, 11, 5) not in result.removed
    assert lease.rent_periods.filter(effective_from=dt.date(2027, 11, 5)).exists()


def test_a_stated_amount_must_fall_on_a_rent_due_date_inside_the_term():
    lease = a_live_tenancy(template=LeaseTemplate.STATED)

    with pytest.raises(ValidationError):
        lease_services.add_rent_period(
            lease, effective_from=dt.date(2022, 6, 7), amount=Decimal("1450.00")
        )

    with pytest.raises(ValidationError):
        lease_services.add_rent_period(
            lease, effective_from=dt.date(2030, 6, 1), amount=Decimal("1450.00")
        )


def test_a_fixed_lease_has_nothing_to_state():
    lease = make_lease(template=LeaseTemplate.FIXED, start_date=TODAY, billing_start_date=None)

    with pytest.raises(ValidationError, match="one rent for its term"):
        lease_services.add_rent_period(
            lease, effective_from=TODAY.replace(day=1), amount=Decimal("100.00")
        )


def test_a_stated_amount_can_be_removed_while_nothing_is_charged():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)
    period = lease_services.add_rent_period(
        lease, effective_from=dt.date(2022, 6, 1), amount=Decimal("1450.00")
    )

    lease_services.remove_rent_period(period)

    assert not lease.rent_periods.exists()


def test_a_charged_amount_cannot_be_removed():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=dt.date(2022, 6, 1))
    period = lease_services.add_rent_period(
        lease, effective_from=dt.date(2022, 6, 1), amount=Decimal("1450.00")
    )
    ledger_services.generate_charges(lease, through=dt.date(2022, 6, 30))

    with pytest.raises(ValidationError, match="already been charged"):
        lease_services.remove_rent_period(period)


# --- the screens ----------------------------------------------------------


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="starting-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="starting-manager"))
    return client


def test_the_lease_page_asks_for_the_starting_account(as_admin):
    lease = a_live_tenancy()

    body = " ".join(
        strip_tags(
            as_admin.get(
                reverse("leases:lease-detail", args=[lease.pk]), {"section": "terms"}
            ).content.decode()
        ).split()
    )

    assert "Set starting account balance" in body
    assert "Earlier bills and payments are not recreated" in body


def test_a_retired_e4_payload_cannot_recreate_bills_through_the_screen(as_admin):
    """The old HISTORY payload is not a second way in; it writes nothing at all."""
    lease = a_live_tenancy()

    response = as_admin.post(
        reverse("leases:onboard", args=[lease.pk]),
        {
            "method": "HISTORY",
            "as_of": TODAY.isoformat(),
            "received_total": "60000.00",
            "opening_amount": "",
            "billing_start_date": lease.start_date.isoformat(),
            "note": "Bank transfers since 2022",
        },
    )

    assert response.status_code == 200
    lease.refresh_from_db()
    assert lease.billing_start_date is None
    assert not lease.payments.exists()
    assert not lease.charges.exists()


def test_an_admin_states_a_rent_amount_through_the_screen(as_admin):
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)

    response = as_admin.post(
        reverse("leases:rent-period-create", args=[lease.pk]),
        {"effective_from": "2022-06-01", "amount": "1450.00", "note": "As the lease states"},
    )

    assert response.status_code == 302
    period = lease.rent_periods.get()
    assert period.amount == Decimal("1450.00")
    assert period.origin == RentPeriodOrigin.MANUAL


def test_a_manager_can_open_the_starting_account_screen(as_manager):
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)

    assert as_manager.get(reverse("leases:onboard", args=[lease.pk])).status_code == 200
    assert (
        as_manager.post(
            reverse("leases:rent-period-create", args=[lease.pk]),
            {"effective_from": "2022-06-01", "amount": "1450.00", "note": ""},
        ).status_code
        == 302
    )


def test_a_tenant_never_reaches_the_starting_account_screen(client):
    lease = a_live_tenancy()
    client.force_login(make_tenant(username="ada"))

    assert client.get(reverse("leases:onboard", args=[lease.pk])).status_code == 403


def test_the_ledger_says_why_it_will_not_charge(as_manager):
    lease = a_live_tenancy()

    response = as_manager.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    body = " ".join(strip_tags(response.content.decode()).split())
    assert "Record its starting account balance" in body
    assert not lease.charges.exists()


def test_the_tenant_statement_shows_a_brought_forward_balance(client):
    tenant = make_tenant(username="ada")
    lease = a_live_tenancy(tenants=[tenant], billing_start_date=None)
    place_lease(lease, make_admin(username="starting-placer"), kind="DEBT", amount="1450.00")
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("payments:home")).content.decode()).split())

    assert "Balance brought forward" in body
    assert "$1,450.00" in body
