"""What is owed, and since when: arrears, and what only looks late.

The boundary matters more than the arithmetic here. A charge is past due because
its date has passed *and* money is still owed on it; a charge due today is due now
but not late; a payment that is merely expected never counts as money; and a charge
that is already covered is never the next thing due (ADR-012).
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


def test_a_charge_due_today_is_due_now_but_not_late():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.UNPAID
    assert ledger.due_now == Decimal("100.00")
    assert ledger.arrears == Decimal("0.00")
    assert ledger.has_arrears is False


def test_a_charge_due_yesterday_is_past_due():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.arrears == Decimal("100.00")
    assert ledger.has_arrears is True
    assert ledger.due_now == Decimal("100.00"), "late money is still owed now"


def test_a_future_charge_is_billed_but_not_due():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TOMORROW)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.UNPAID
    assert ledger.due_now == Decimal("0.00")
    assert ledger.arrears == Decimal("0.00")
    assert ledger.not_yet_due == Decimal("100.00"), "stated, never headlined"


def test_a_paid_late_charge_is_not_past_due():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.PAID
    assert ledger.arrears == Decimal("0.00")
    assert ledger.due_now == Decimal("0.00")


def test_a_partly_paid_late_charge_is_past_due_for_the_rest():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    make_payment(lease, amount=Decimal("40.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.arrears == Decimal("60.00")


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
    assert ledger.arrears == Decimal("100.00")
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
    assert ledger.arrears == Decimal("100.00")


def test_a_credit_against_a_late_charge_is_not_itself_past_due():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=YESTERDAY)
    adjustment = services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("25.00"), reason="overcharged"
    )

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("75.00")
    assert ledger.arrears == Decimal("75.00"), "the credit settles its own charge"
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert state_of(ledger, adjustment) == ChargeState.ADJUSTMENT


def test_arrears_is_the_sum_of_every_late_charge():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=40))
    make_charge(lease, amount=Decimal("50.00"), due_date=YESTERDAY)
    make_charge(lease, amount=Decimal("999.00"), due_date=TOMORROW)

    ledger = ledger_for(lease)
    assert ledger.arrears == Decimal("150.00")
    assert ledger.due_now == Decimal("150.00")
    assert ledger.not_yet_due == Decimal("999.00")


def test_an_ended_lease_can_still_be_past_due():
    """Ending a tenancy does not forgive what it owed."""
    lease = make_lease(
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=60))

    ledger = ledger_for(lease)
    assert state_of(ledger, charge) == ChargeState.OVERDUE
    assert ledger.arrears == Decimal("100.00")
    assert ledger.next_charge is None, "nothing more falls due on an ended lease"


def test_a_tenancy_paid_ahead_shows_a_credit_not_a_debt():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("250.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("-150.00")
    assert ledger.credit == Decimal("150.00")
    assert ledger.arrears == Decimal("0.00")
    assert ledger.due_now == Decimal("0.00")


def test_the_next_charge_is_the_soonest_charge_still_owing():
    lease = make_lease()
    later = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY + dt.timedelta(days=30))
    soonest = make_charge(lease, amount=Decimal("50.00"), due_date=TOMORROW)
    # Behind today's line: the oldest money is arrears, not the coming due figure.
    make_charge(lease, amount=Decimal("10.00"), due_date=TODAY - dt.timedelta(days=5))

    ledger = ledger_for(lease)
    assert ledger.next_charge.date == soonest.due_date
    assert ledger.next_charge.left == Decimal("50.00")
    assert ledger.next_charge.date != later.due_date


def test_a_settled_charge_is_never_the_next_charge():
    """A charge already covered is not something to look forward to paying."""
    lease = make_lease()
    covered = make_charge(lease, amount=Decimal("100.00"), due_date=TOMORROW)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    after = make_charge(lease, amount=Decimal("120.00"), due_date=TODAY + dt.timedelta(days=31))

    ledger = ledger_for(lease)
    assert ledger.next_charge.date == after.due_date, "the covered month is skipped"
    assert ledger.next_charge.date != covered.due_date


def test_the_next_charge_carries_what_is_left_not_the_gross():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TOMORROW)
    make_payment(lease, amount=Decimal("40.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.next_charge.date == charge.due_date
    assert ledger.next_charge.left == Decimal("60.00")


def test_arrears_oldest_names_the_oldest_unpaid_charge_and_its_age():
    lease = make_lease()
    make_charge(lease, amount=Decimal("50.00"), due_date=TODAY - dt.timedelta(days=10))
    oldest = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=40))
    make_charge(lease, amount=Decimal("999.00"), due_date=TOMORROW)

    ledger = ledger_for(lease)
    assert ledger.arrears_oldest.date == oldest.due_date
    assert ledger.arrears_age_days == 40


def test_a_tenancy_with_no_arrears_has_no_oldest_charge():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_charge(lease, amount=Decimal("100.00"), due_date=TOMORROW)

    ledger = ledger_for(lease)
    assert ledger.arrears_oldest is None
    assert ledger.arrears_age_days is None
    assert ledger.has_arrears is False
