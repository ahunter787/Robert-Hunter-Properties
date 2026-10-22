"""One allocation engine: recorded applications must reproduce the oldest-first rule.

The read-time projection is gone (ADR-028 D3). This file is the regression harness for the
surviving engine: a frozen reference implementation of oldest-first allocation, and the
one-time migration that wrote legacy implied coverage down as applications. Together they
prove that snapping a tenancy's coverage into rows changes no figure the desk or the tenant
reads, and that reading a ledger never allocates on the fly.

The reference is deliberately *in the test*, not imported from production code: it is the
specification of the rule, so a change to the production engine has to argue with it.
"""

import datetime as dt
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import (
    ChargeKind,
    Direction,
    FundsApplication,
    Payment,
    PaymentKind,
    PaymentStatus,
)
from tests.factories import make_charge, make_lease

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")


# --- the frozen reference -------------------------------------------------


def _reference(lease):
    """The oldest-first rule, written out: per-charge settled and pending coverage."""
    charges = list(lease.charges.order_by("due_date", "pk"))
    payments = list(lease.payments.order_by("payment_date", "pk"))

    corrected = {}
    for charge in charges:
        if charge.adjusts_id is not None:
            corrected[charge.adjusts_id] = corrected.get(charge.adjusts_id, ZERO) + (
                charge.balance_effect
            )

    lines = [
        {
            "pk": charge.pk,
            "kind": charge.kind,
            "due_date": charge.due_date,
            "net": charge.balance_effect + corrected.get(charge.pk, ZERO),
            "settled": ZERO,
            "pending": ZERO,
        }
        for charge in charges
    ]
    reversed_ids = {payment.reverses_id for payment in payments if payment.reverses_id}
    effective = [
        payment.amount
        for payment in payments
        if payment.kind == PaymentKind.RECEIVED
        and payment.status == PaymentStatus.CLEARED
        and payment.pk not in reversed_ids
    ]
    pending = [
        payment.amount
        for payment in payments
        if payment.kind == PaymentKind.RECEIVED and payment.status == PaymentStatus.PENDING
    ]
    opening_credits = [
        -line["net"] for line in lines if line["kind"] == ChargeKind.OPENING and line["net"] < ZERO
    ]

    def allocate(amounts, *, is_pending):
        pool = sum(amounts, ZERO)
        if pool <= ZERO:
            return
        for line in sorted(lines, key=lambda item: (item["due_date"], item["pk"])):
            if line["kind"] == ChargeKind.ADJUSTMENT or line["net"] <= ZERO:
                # A correction is not something a payment settles; the charge it names
                # carries the money (the same rule the production code states).
                continue
            filled = (line["settled"] + line["pending"]) if is_pending else line["settled"]
            remaining = line["net"] - filled
            if remaining <= ZERO:
                continue
            applied = min(remaining, pool)
            if is_pending:
                line["pending"] += applied
            else:
                line["settled"] += applied
            pool -= applied
            if pool <= ZERO:
                return

    allocate(effective + opening_credits, is_pending=False)
    allocate(pending, is_pending=True)
    return {line["pk"]: line for line in lines}


def _expected_balance(lease):
    charges = list(lease.charges.all())
    payments = list(lease.payments.all())
    reversed_ids = {payment.reverses_id for payment in payments if payment.reverses_id}
    paid = sum(
        (
            payment.amount
            for payment in payments
            if payment.kind == PaymentKind.RECEIVED
            and payment.status == PaymentStatus.CLEARED
            and payment.pk not in reversed_ids
        ),
        ZERO,
    )
    charged = sum((charge.balance_effect for charge in charges), ZERO)
    return charged - paid


def _figures(ledger):
    return (
        ledger.balance_due,
        ledger.due_now,
        ledger.credit,
        ledger.arrears,
        ledger.not_yet_due,
        ledger.unpaid_charges,
    )


def _coverage(ledger, *, pending=False):
    return {line.charge.pk: line.pending if pending else line.settled for line in ledger.charges}


def _snapshot():
    """Run the one-time migration's snapshot against the test database."""
    migration = import_module("apps.ledger.migrations.0009_single_allocation_engine")
    migration.snapshot(apps, SimpleNamespace(connection=connection))


def _payment(lease, *, amount, payment_date=None, status=PaymentStatus.CLEARED, **fields):
    """A raw payment row: histories written before the engine existed never allocated."""
    return Payment.objects.create(
        lease=lease,
        amount=amount,
        payment_date=payment_date or TODAY,
        method=fields.pop("method", "ACH"),
        status=status,
        **fields,
    )


def _assert_agreement(lease):
    reference = _reference(lease)

    # A read does not allocate: without recorded applications the coverage is empty.
    unallocated = services.build_ledger(lease)
    assert _coverage(unallocated) == dict.fromkeys(reference, ZERO)
    assert unallocated.balance_due == _expected_balance(lease)

    # The one-time migration writes the implied coverage down once...
    _snapshot()
    recorded = services.build_ledger(lease)
    expected_covered = any(row["settled"] > ZERO for row in reference.values())
    assert FundsApplication.objects.filter(lease=lease).exists() == expected_covered
    assert _coverage(recorded) == {pk: row["settled"] for pk, row in reference.items()}
    assert _coverage(recorded, pending=True) == {
        pk: row["pending"] for pk, row in reference.items()
    }
    assert recorded.balance_due == _expected_balance(lease)
    assert recorded.credit == max(-_expected_balance(lease), ZERO)

    # ...and re-running it is a no-op: the rows are the record now.
    counts = (FundsApplication.objects.filter(lease=lease).count(), lease.payments.count())
    _snapshot()
    assert counts == (FundsApplication.objects.filter(lease=lease).count(), lease.payments.count())
    assert _figures(services.build_ledger(lease)) == _figures(recorded)

    # Every obligation reads the same coverage the charge line does (no plans here).
    # An obligation exists for a bill that asks for money; a correction and a credit
    # line are not billed and carry no obligation.
    paid = {}
    for obligation in recorded.obligations:
        paid[obligation.charge.pk] = paid.get(obligation.charge.pk, ZERO) + obligation.paid
    billable = {
        pk: row["settled"]
        for pk, row in reference.items()
        if row["kind"] != ChargeKind.ADJUSTMENT and row["net"] > ZERO
    }
    assert paid == billable


# --- histories ------------------------------------------------------------


def _lease():
    return make_lease(start_date=TODAY, end_date=TODAY + dt.timedelta(days=400))


def test_single_bill_part_paid():
    lease = _lease()
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    _payment(lease, amount=Decimal("400"))
    _assert_agreement(lease)


def test_bills_out_of_order_oldest_first():
    lease = _lease()
    make_charge(lease, amount=Decimal("500"), due_date=TODAY - dt.timedelta(days=30))
    make_charge(lease, amount=Decimal("700"), due_date=TODAY - dt.timedelta(days=60))
    make_charge(lease, amount=Decimal("300"), due_date=TODAY)
    _payment(lease, amount=Decimal("900"))
    _assert_agreement(lease)


def test_overpayment_is_held_credit():
    lease = _lease()
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    _payment(lease, amount=Decimal("1200"))
    _assert_agreement(lease)


def test_opening_credit_settles_oldest_bill_then_stays_held():
    lease = _lease()
    make_charge(
        lease,
        amount=Decimal("200"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        direction=Direction.DECREASE,
        description="Opening credit",
    )
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    _assert_agreement(lease)


def test_opening_credit_fully_used():
    lease = _lease()
    make_charge(
        lease,
        amount=Decimal("200"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        direction=Direction.DECREASE,
        description="Opening credit",
    )
    make_charge(lease, amount=Decimal("100"), due_date=TODAY)
    _assert_agreement(lease)


def test_reducing_adjustment_naming_its_charge():
    lease = _lease()
    charge = make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    make_charge(
        lease,
        amount=Decimal("300"),
        due_date=TODAY,
        kind=ChargeKind.ADJUSTMENT,
        direction=Direction.DECREASE,
        description="Overcharge",
        adjusts=charge,
        reason="Overcharge corrected",
    )
    _payment(lease, amount=Decimal("400"))
    _assert_agreement(lease)


def test_increasing_adjustment_naming_its_charge():
    lease = _lease()
    charge = make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    make_charge(
        lease,
        amount=Decimal("200"),
        due_date=TODAY,
        kind=ChargeKind.ADJUSTMENT,
        direction=Direction.INCREASE,
        description="Undercharge",
        adjusts=charge,
        reason="Undercharge corrected",
    )
    _payment(lease, amount=Decimal("400"))
    _assert_agreement(lease)


def test_reversed_payment_moves_nothing():
    lease = _lease()
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    payment = _payment(lease, amount=Decimal("1000"))
    _payment(
        lease,
        amount=Decimal("1000"),
        kind=PaymentKind.REVERSAL,
        reverses=payment,
        method="OTHER",
        reason="Wrong receipt",
    )
    _assert_agreement(lease)


def test_pending_money_marks_but_does_not_settle():
    lease = _lease()
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    _payment(lease, amount=Decimal("300"), status=PaymentStatus.PENDING)
    _payment(lease, amount=Decimal("200"))
    _assert_agreement(lease)


def test_unknown_aging_stays_out_of_dated_arrears():
    lease = _lease()
    make_charge(
        lease,
        amount=Decimal("11500"),
        due_date=TODAY - dt.timedelta(days=60),
        kind=ChargeKind.OPENING,
        aging_unknown=True,
        description="Brought forward",
    )
    _payment(lease, amount=Decimal("500"))
    _assert_agreement(lease)


def test_payment_only_history_is_credit():
    lease = _lease()
    _payment(lease, amount=Decimal("500"))
    _assert_agreement(lease)


def test_bills_due_in_the_future_are_not_due_now():
    lease = _lease()
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY + dt.timedelta(days=20))
    _payment(lease, amount=Decimal("100"))
    _assert_agreement(lease)
