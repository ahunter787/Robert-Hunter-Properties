"""E2: property responsibilities — the bill, the cycle, and each unit's share.

The coverage rule is the one that matters: "which months does this bill pay for?"
has exactly one answer here, and it is what the ledger charges. Nothing re-derives a
percentage at charge time, and nothing that has been charged is rewritten.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.responsibilities import services
from apps.responsibilities.models import ResponsibilityCategory
from tests.factories import (
    make_cycle,
    make_lease,
    make_property,
    make_responsibility,
    make_share,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def two_unit_property(*, sizes=(760, 240)):
    """A property like the owner's: two units whose sizes divide the bills 76/24."""
    property_obj = make_property(name="Two Unit Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=sizes[0])
    second = make_unit(for_property=property_obj, identifier="2", square_feet=sizes[1])
    return property_obj, first, second


# --- the model ------------------------------------------------------------


def test_a_property_sums_its_units_sizes():
    property_obj, first, second = two_unit_property()

    assert property_obj.total_square_feet == 1000
    assert first.share_of_property == Decimal("76.00")
    assert second.share_of_property == Decimal("24.00")


def test_without_sizes_there_is_no_share_to_claim():
    property_obj = make_property(name="Unmeasured")
    unit = make_unit(for_property=property_obj, square_feet=None)

    assert property_obj.total_square_feet is None
    assert unit.share_of_property is None


def test_a_label_is_unique_on_a_property():
    from django.db import IntegrityError

    property_obj, _first, _second = two_unit_property()
    make_responsibility(property_obj, label="Water")

    with pytest.raises(IntegrityError):
        make_responsibility(property_obj, label="Water")


def test_a_cycle_is_between_one_and_twelve_months():
    property_obj, _first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)

    with pytest.raises(ValidationError):
        make_cycle(responsibility, months=13)

    with pytest.raises(ValidationError):
        make_cycle(responsibility, months=0)


def test_a_unit_from_another_property_cannot_carry_a_share():
    property_obj, _first, _second = two_unit_property()
    other_unit = make_unit(identifier="Elsewhere", square_feet=500)
    cycle = make_cycle(make_responsibility(property_obj))

    with pytest.raises(ValidationError):
        make_share(cycle, other_unit)


def test_the_monthly_total_is_the_bill_divided_across_its_months():
    property_obj, _first, _second = two_unit_property()
    cycle = make_cycle(make_responsibility(property_obj), months=3, total_amount=Decimal("788.00"))

    assert cycle.monthly_total == Decimal("262.67")


# --- which months a cycle covers ------------------------------------------


def test_a_quarterly_cycle_covers_three_months_from_its_start():
    property_obj, first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)
    lease = make_lease(
        first, start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31), rent_due_day=5
    )
    cycle = make_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), months=3, total_amount=Decimal("600.00")
    )

    assert cycle.covered_dates(lease) == [
        dt.date(2027, 5, 5),
        dt.date(2027, 6, 5),
        dt.date(2027, 7, 5),
    ]
    assert cycle.covers(dt.date(2027, 6, 5), lease)
    assert not cycle.covers(dt.date(2027, 8, 5), lease)


def test_a_cycle_starting_mid_month_takes_the_next_due_date():
    property_obj, first, _second = two_unit_property()
    lease = make_lease(
        first, start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31), rent_due_day=1
    )
    cycle = make_cycle(make_responsibility(property_obj), starts_on=dt.date(2027, 5, 15), months=2)

    assert cycle.covered_dates(lease) == [dt.date(2027, 6, 1), dt.date(2027, 7, 1)]


def test_a_cycle_stops_at_the_end_of_the_tenancy():
    property_obj, first, _second = two_unit_property()
    lease = make_lease(
        first, start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 5, 31), rent_due_day=5
    )
    cycle = make_cycle(make_responsibility(property_obj), starts_on=dt.date(2027, 4, 5), months=3)

    assert cycle.covered_dates(lease) == [dt.date(2027, 4, 5), dt.date(2027, 5, 5)]


def test_the_current_and_staged_cycles_are_read_from_the_dates():
    property_obj, _first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)
    last_month = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    next_month = (TODAY.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    behind = make_cycle(
        responsibility, starts_on=last_month, months=3, total_amount=Decimal("300.00")
    )
    ahead = make_cycle(
        responsibility, starts_on=next_month, months=3, total_amount=Decimal("330.00")
    )

    assert responsibility.current_cycle() == behind
    assert responsibility.next_cycle() == ahead
    assert responsibility.cycle_covering(TODAY) == behind


# --- staging --------------------------------------------------------------


def test_staging_proposes_shares_from_floor_area():
    property_obj, first, second = two_unit_property()
    responsibility = make_responsibility(property_obj, cycle_months=3)

    cycle = services.stage_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), total_amount=Decimal("600.00")
    )

    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares[first.pk] == Decimal("152.00"), "76% of 200"
    assert shares[second.pk] == Decimal("48.00"), "24% of 200"


def test_staging_splits_evenly_when_no_size_is_recorded():
    property_obj = make_property(name="Unmeasured")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=None)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=None)
    responsibility = make_responsibility(property_obj)

    cycle = services.stage_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), total_amount=Decimal("300.00"), months=3
    )

    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares[first.pk] == Decimal("50.00")
    assert shares[second.pk] == Decimal("50.00")


def test_the_office_can_override_a_unit_amount():
    """The real water case: one unit's usage billed, the other carrying the rest."""
    property_obj, first, second = two_unit_property()
    responsibility = make_responsibility(property_obj)

    cycle = services.stage_cycle(
        responsibility,
        starts_on=dt.date(2027, 5, 5),
        total_amount=Decimal("600.00"),
        amounts_by_unit={first.pk: Decimal("80.00"), second.pk: Decimal("120.00")},
    )

    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares[first.pk] == Decimal("80.00")
    assert shares[second.pk] == Decimal("120.00")


def test_a_zero_takes_a_unit_out_of_the_cycle():
    property_obj, first, second = two_unit_property()
    responsibility = make_responsibility(property_obj)
    cycle = services.stage_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), total_amount=Decimal("600.00")
    )

    services.set_shares(cycle, {first.pk: Decimal("0.00"), second.pk: Decimal("200.00")})

    assert [share.unit_id for share in cycle.shares.all()] == [second.pk]


def test_staging_the_same_start_date_again_updates_the_bill():
    property_obj, _first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)
    services.stage_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), total_amount=Decimal("600.00")
    )

    cycle = services.stage_cycle(
        responsibility, starts_on=dt.date(2027, 5, 5), total_amount=Decimal("900.00")
    )

    assert responsibility.cycles.count() == 1
    assert cycle.total_amount == Decimal("900.00")
    assert cycle.monthly_total == Decimal("300.00")


def test_a_unit_outside_the_property_is_refused():
    property_obj, first, _second = two_unit_property()
    outsider = make_unit(identifier="Elsewhere", square_feet=500)
    responsibility = make_responsibility(property_obj)

    with pytest.raises(ValidationError):
        services.stage_cycle(
            responsibility,
            starts_on=dt.date(2027, 5, 5),
            total_amount=Decimal("600.00"),
            amounts_by_unit={outsider.pk: Decimal("10.00")},
        )


def test_a_negative_share_is_refused():
    property_obj, first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)

    with pytest.raises(ValidationError):
        services.stage_cycle(
            responsibility,
            starts_on=dt.date(2027, 5, 5),
            total_amount=Decimal("600.00"),
            amounts_by_unit={first.pk: Decimal("-1.00")},
        )


def test_saving_a_responsibility_records_who_did_it():
    from apps.audit.models import AuditAction, AuditEvent

    property_obj, _first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj, label="Water")

    services.save_responsibility(
        responsibility,
        label="Water",
        category=ResponsibilityCategory.MAINTENANCE,
        cycle_months=6,
        is_active=True,
    )

    event = AuditEvent.objects.filter(action=AuditAction.RESPONSIBILITY_CHANGED).first()
    assert event is not None
    assert "maintenance" in event.summary
    assert event.metadata["cycle_months"] == 6


def test_an_unknown_category_is_refused():
    property_obj, _first, _second = two_unit_property()
    responsibility = make_responsibility(property_obj)

    with pytest.raises(ValidationError):
        services.save_responsibility(
            responsibility, label="Water", category="SOMETHING", cycle_months=3, is_active=True
        )
