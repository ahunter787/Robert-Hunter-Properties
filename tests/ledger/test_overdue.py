"""Overdue determination: what is late, and what only looks late.

The boundary matters more than the arithmetic here — a charge is overdue because
its date has passed *and* money is still owed on it, and a payment that is merely
expected never counts as money.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.leases.models import LeaseStatus
from apps.ledger import services
from apps.ledger.models import ChargeState, Direction, PaymentStatus
from tests.factories import make_charge, make_lease, make_payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
YESTERDAY = TODAY - dt.timedelta(days=1)
TOMORROW = TODAY + dt.timedelta(days=1)


def ledger_for(lease):
    return services.build_ledger(lease)


def state_of(ledger, charge):
    return next(line.state for line in ledger.charges if line.charge.pk == charge.pk)


def test_a_charge_due_today_is_not_overdue():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.UNPAID
    assert ledger.overdue_amount == Decimal("0.00")
    assert ledger.is_overdue is False


def test_a_charge_due_yesterday_is_overdue():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.overdue_amount == Decimal("100.00")
    assert ledger.is_overdue is True


def test_a_future_charge_is_never_overdue():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TOMORROW)

    assert state_of(ledger_for(lease), charge) == ChargeState.UNPAID


def test_a_paid_late_charge_is_not_overdue():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.PAID
    assert ledger.overdue_amount == Decimal("0.00")


def test_a_partly_paid_late_charge_is_overdue_for_the_rest():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    make_payment(lease, amount=Decimal("40.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.overdue_amount == Decimal("60.00")


def test_an_expected_payment_does_not_stop_a_charge_being_late():
    """A promise is not money: the desk needs to see it is still unreceived."""
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)

    # A pending payment, a week late itself.
    make_payment(
        lease,
        amount=Decimal("100.00"),
        payment_date=TODAY - dt.timedelta(days=7),
        status=PaymentStatus.PENDING,
    )

    ledger = ledger_for(lease)
    assert ledger.overdue_amount == Decimal("100.00")
    assert ledger.balance_due == Decimal("100.00")
    assert state_of(ledger, charge) == ChargeState.PENDING


def test_a_void_payment_changes_nothing():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    payment = make_payment(
        lease,
        amount=Decimal("100.00"),
        payment_date=TODAY,
        status=PaymentStatus.PENDING,
    )
    services.void_payment(payment)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.overdue_amount == Decimal("100.00")


def test_a_credit_against_a_late_charge_is_not_itself_overdue():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    adjustment = services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("25.00"), reason="overcharged"
    )

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("75.00")
    assert ledger.overdue_amount == Decimal("75.00"), "the credit settles its own charge"
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert state_of(ledger, adjustment) == ChargeState.ADJUSTMENT


def test_overdue_is_the_sum_of_every_late_charge():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=40))
    make_charge(lease, amount=Decimal("50.00"), due_date=YESTERDAY)
    make_charge(lease, amount=Decimal("999.00"), due_date=TOMORROW)

    assert ledger_for(lease).overdue_amount == Decimal("150.00")


def test_an_ended_lease_can_still_be_overdue():
    """Ending a tenancy does not forgive what it owed."""
    lease = make_lease(
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=60))

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.overdue_amount == Decimal("100.00")


def test_a_tenancy_paid_ahead_shows_a_credit_not_a_debt():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("250.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("-150.00")
    assert ledger.credit == Decimal("150.00")
    assert ledger.overdue_amount == Decimal("0.00")


def test_next_due_is_the_soonest_unsettled_charge():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY + dt.timedelta(days=30))
    soonest = make_charge(lease, amount=Decimal("50.00"), due_date=TODAY)
    settled = make_charge(lease, amount=Decimal("10.00"), due_date=TODAY - dt.timedelta(days=5))
    make_payment(lease, amount=Decimal("10.00"), payment_date=TODAY)

    ledger = ledger_for(lease)

    assert ledger.next_due.charge.pk == soonest.pk
    assert settled.pk != ledger.next_due.charge.pk
