"""E2: a property's bills reaching the tenant's ledger.

One charge per responsibility per month, at the amount the office stored for the
unit — never a percentage re-applied at charge time — and nothing raised twice.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.leases import services as lease_services
from apps.ledger import services as ledger_services
from apps.ledger.models import Charge, ChargeKind
from apps.responsibilities import services
from apps.responsibilities.models import ResponsibilityCategory
from tests.factories import (
    make_charge,
    make_cycle,
    make_lease,
    make_nnn_rate,
    make_property,
    make_responsibility,
    make_share,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
#: The desk charges through the end of next month by default, so a cycle's months
#: are covered the way the office covers them.
HORIZON = ledger_services.generation_horizon(1)


def a_billed_property(*, total="600.00", months=3, first_amount="152.00", second_amount="48.00"):
    """Two units, one quarterly water bill, shares stored for the cycle."""
    property_obj = make_property(name="Billed Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=240)
    responsibility = make_responsibility(property_obj, label="Water", cycle_months=months)
    start = TODAY.replace(day=1)
    cycle = make_cycle(responsibility, starts_on=start, months=months, total_amount=Decimal(total))
    make_share(cycle, first, monthly_amount=Decimal(first_amount))
    make_share(cycle, second, monthly_amount=Decimal(second_amount))
    return property_obj, first, second, responsibility, cycle


def a_lease_on(unit, **fields):
    fields.setdefault("start_date", TODAY.replace(day=1) - dt.timedelta(days=40))
    fields.setdefault("end_date", TODAY + dt.timedelta(days=400))
    fields.setdefault("rent_due_day", 1)
    fields.setdefault("monthly_rent", Decimal("1000.00"))
    return make_lease(unit, **fields)


def test_a_units_share_is_charged_every_month_of_the_cycle():
    _property, first, _second, _responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first)

    created = ledger_services.generate_charges(lease, through=HORIZON)
    charges = [charge for charge in created if charge.kind == ChargeKind.RESPONSIBILITY]

    assert [charge.amount for charge in charges] == [Decimal("152.00")] * 2, "this month and next"
    assert all(charge.responsibility_id is not None for charge in charges)
    assert charges[0].description.startswith("Water for ")


def test_the_office_figure_is_what_is_charged_not_a_percentage():
    """The stored override wins: 80/120, not 76%/24% of the bill."""
    property_obj, first, second, responsibility, cycle = a_billed_property()
    services.set_shares(cycle, {first.pk: Decimal("80.00"), second.pk: Decimal("120.00")})
    first_lease = a_lease_on(first)
    second_lease = a_lease_on(second)

    ledger_services.generate_charges(first_lease, through=TODAY)
    ledger_services.generate_charges(second_lease, through=TODAY)

    assert first_lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).first().amount == Decimal(
        "80.00"
    )
    assert second_lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).first().amount == Decimal(
        "120.00"
    )


def test_generating_twice_creates_nothing_twice():
    _property, first, _second, _responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first)
    created = ledger_services.generate_charges(lease, through=HORIZON)

    again = ledger_services.generate_charges(lease, through=HORIZON)

    assert created
    assert again == []
    assert lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).count() == 2


def test_a_unit_with_no_share_carries_nothing():
    property_obj, first, _second, responsibility, _cycle = a_billed_property()
    third = make_unit(for_property=property_obj, identifier="3", square_feet=100)
    lease = a_lease_on(third)

    ledger_services.generate_charges(lease, through=TODAY)

    assert not lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).exists()


def test_a_share_of_zero_carries_nothing():
    _property, first, _second, _responsibility, cycle = a_billed_property()
    services.set_shares(cycle, {first.pk: Decimal("0.00")})
    lease = a_lease_on(first)

    ledger_services.generate_charges(lease, through=TODAY)

    assert not lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).exists()


def test_a_stopped_responsibility_raises_nothing_new():
    _property, first, _second, responsibility, _cycle = a_billed_property()
    responsibility.is_active = False
    responsibility.save(update_fields=["is_active"])
    lease = a_lease_on(first)

    ledger_services.generate_charges(lease, through=TODAY)

    assert not lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).exists()


def test_months_after_the_cycle_starts_are_not_covered():
    _property, first, _second, responsibility, _cycle = a_billed_property(months=1)
    lease = a_lease_on(first)

    ledger_services.generate_charges(lease, through=TODAY + dt.timedelta(days=60))

    assert lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).count() == 1


def test_rent_nnn_and_a_responsibility_can_share_a_due_date():
    property_obj, first, _second, _responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first, template="NNN", step_up_month=1, step_up_percent=Decimal("0.00"))
    make_nnn_rate(
        lease,
        effective_from=lease_services.first_due_on_or_after(lease, lease.start_date),
        monthly_amount=Decimal("200.00"),
    )

    ledger_services.generate_charges(lease, through=HORIZON)

    kinds = set(lease.charges.values_list("kind", flat=True))
    assert kinds == {ChargeKind.RENT, ChargeKind.NNN, ChargeKind.RESPONSIBILITY}


def test_the_ledger_reads_the_new_charges_like_any_other():
    _property, first, _second, _responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first)
    ledger_services.generate_charges(lease, through=HORIZON)

    ledger = ledger_services.build_ledger(lease)

    assert ledger.not_yet_due > Decimal("0.00")
    rows = [row for row in ledger.statement_charges if row.charge_kind == ChargeKind.RESPONSIBILITY]
    assert rows
    assert rows[0].title.startswith("Water for ")
    total = sum((row.amount for row in rows), Decimal("0.00"))
    assert total == Decimal("304.00"), "two months at 152.00"


def test_a_responsibility_charge_must_name_its_cost():
    _property, first, _second, _responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first)

    with pytest.raises(ValidationError):
        Charge.objects.create(
            lease=lease,
            kind=ChargeKind.RESPONSIBILITY,
            description="Water for ever",
            amount=Decimal("10.00"),
            due_date=TODAY,
        )


# --- once charged, the cycle is history -----------------------------------


def test_a_charged_cycle_cannot_be_restaged():
    _property, first, _second, responsibility, cycle = a_billed_property()
    lease = a_lease_on(first)
    ledger_services.generate_charges(lease, through=TODAY)

    with pytest.raises(ValidationError, match="already been charged"):
        services.stage_cycle(
            responsibility,
            starts_on=cycle.starts_on,
            total_amount=Decimal("900.00"),
            months=3,
        )


def test_a_charged_cycles_shares_cannot_be_changed():
    _property, first, _second, _responsibility, cycle = a_billed_property()
    lease = a_lease_on(first)
    ledger_services.generate_charges(lease, through=TODAY)

    with pytest.raises(ValidationError, match="already been charged"):
        services.set_shares(cycle, {first.pk: Decimal("99.00")})


def test_a_cycle_before_its_months_is_still_editable():
    _property, first, _second, responsibility, _cycle = a_billed_property()
    other = make_cycle(
        responsibility,
        starts_on=TODAY.replace(day=1) + dt.timedelta(days=90),
        months=3,
        total_amount=Decimal("600.00"),
    )

    services.set_shares(other, {first.pk: Decimal("10.00")})

    assert other.shares.get(unit=first).monthly_amount == Decimal("10.00")


def test_the_property_overview_shows_who_carries_what():
    _property, first, second, _responsibility, _cycle = a_billed_property()
    a_lease_on(first)
    property_obj = first.property

    rows = services.property_overview(property_obj)

    assert len(rows) == 1
    row = rows[0]
    assert row.monthly_total == Decimal("200.00")
    assert row.allocated_monthly == Decimal("200.00")
    assert row.landlord_monthly == Decimal("0.00")
    by_unit = {share.unit.identifier: share for share in row.shares}
    assert by_unit["1"].has_lease is True
    assert by_unit["2"].has_lease is False
    assert by_unit["1"].monthly_amount == Decimal("152.00")
    assert by_unit["2"].share_of_property == Decimal("24.00")


def test_the_overview_says_what_the_landlord_absorbs():
    property_obj, first, _second, responsibility, _cycle = a_billed_property()
    a_lease_on(first)
    services.set_shares(responsibility.cycles.first(), {first.pk: Decimal("80.00")})

    row = services.property_overview(property_obj)[0]

    assert row.allocated_monthly == Decimal("80.00")
    assert row.landlord_monthly == Decimal("120.00")


def test_a_maintenance_responsibility_is_categorised_for_the_statement():
    property_obj, first, _second, _responsibility, _cycle = a_billed_property()
    make_responsibility(property_obj, label="Pruning", category=ResponsibilityCategory.MAINTENANCE)
    pruning = property_obj.responsibilities.get(label="Pruning")
    cycle = make_cycle(
        pruning, starts_on=TODAY.replace(day=1), months=3, total_amount=Decimal("432.00")
    )
    make_share(cycle, first, monthly_amount=Decimal("144.00"))
    lease = a_lease_on(first)

    ledger_services.generate_charges(lease, through=TODAY)

    ledger = ledger_services.build_ledger(lease)
    pruning_rows = [row for row in ledger.statement_charges if row.title.startswith("Pruning")]
    assert pruning_rows
    assert pruning_rows[0].category == "Maintenance"


def test_a_month_reads_as_past_due_until_every_part_of_it_is_paid():
    """The month's own state is the most pressing thing in it (E2)."""
    _property, first, _second, responsibility, _cycle = a_billed_property()
    lease = a_lease_on(first)
    due = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    make_charge(lease, amount=Decimal("100.00"), due_date=due)
    Charge.objects.create(
        lease=lease,
        kind=ChargeKind.RESPONSIBILITY,
        responsibility=responsibility,
        description="Water",
        amount=Decimal("100.00"),
        due_date=due,
    )
    ledger_services.record_payment(
        lease, amount=Decimal("100.00"), payment_date=TODAY, method="ACH"
    )

    month = next(
        entry
        for entry in ledger_services.build_ledger(lease).statement_months()
        if entry.kind == "month"
    )
    assert month.state_label == "Past due", "the rent is paid; the water is not"

    ledger_services.record_payment(
        lease, amount=Decimal("100.00"), payment_date=TODAY, method="ACH"
    )

    month = next(
        entry
        for entry in ledger_services.build_ledger(lease).statement_months()
        if entry.kind == "month"
    )
    assert month.state_label == "Paid"
    assert month.left == Decimal("0.00")
