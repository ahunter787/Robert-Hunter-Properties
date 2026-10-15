"""The ledger must explain its own balance (audit follow-up, rhp-ledger-integrity).

Two defects came out of the audit's `transactions` projection, and both had the same shape:
the balance and the rows told different stories.

* Adjusting an adjustment was reachable by a direct POST. The nested correction was dropped
  from the rows (they skip anything with an ``adjusts`` link) while still moving the balance:
  a 1,000 charge adjusted to zero and then adjusted back showed **1,000 owed and 0.00 of
  rows**.
* ``ChargeLine`` compared what had been settled against the amount the charge was *raised* at,
  so an increase was invisible to it. A 1,000 charge paid in full and then increased by 200
  read "Paid" while the account was 200 in arrears.

The invariant these tests hold to is the one a person actually relies on: **what the account
says is owed is what its rows add up to.**
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.ledger import services as ledger_services
from apps.ledger.models import ChargeKind, Direction, PaymentStatus
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_payment,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ONE_THOUSAND = Decimal("1000.00")


def a_tenancy(**fields):
    fields.setdefault("start_date", TODAY.replace(day=1) - dt.timedelta(days=90))
    fields.setdefault("end_date", TODAY + dt.timedelta(days=270))
    return make_lease(make_unit(), **fields)


def visible_total(ledger) -> Decimal:
    """What the ledger's own rows add up to: charges shown, less money shown."""
    return sum((row.charge - row.payment_or_credit for row in ledger.transactions), Decimal("0.00"))


# --- the invariant ---------------------------------------------------------


def a_charge_only(lease):
    make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))


def a_charge_partly_paid(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.record_payment(
        lease, amount=Decimal("400.00"), payment_date=TODAY - dt.timedelta(days=5), method="CHECK"
    )
    return charge


def a_charge_paid(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.record_payment(
        lease, amount=ONE_THOUSAND, payment_date=TODAY - dt.timedelta(days=5), method="CHECK"
    )
    return charge


def a_charge_reduced(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("250.00"), reason="agreed reduction"
    )


def a_charge_reduced_to_nothing(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=ONE_THOUSAND, reason="not owed"
    )


def a_charge_increased(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.INCREASE, amount=Decimal("200.00"), reason="under-billed"
    )


def a_paid_charge_increased(lease):
    charge = a_charge_paid(lease)
    ledger_services.create_adjustment(
        charge, direction=Direction.INCREASE, amount=Decimal("200.00"), reason="under-billed"
    )


def a_charge_reduced_then_increased(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("300.00"), reason="too high"
    )
    ledger_services.create_adjustment(
        charge, direction=Direction.INCREASE, amount=Decimal("100.00"), reason="not quite"
    )


def a_charge_and_a_standalone_entry(lease):
    """A correction that names no charge: the model allows an increase, never a credit."""
    make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    make_charge(
        lease,
        kind=ChargeKind.ADJUSTMENT,
        direction=Direction.INCREASE,
        amount=Decimal("150.00"),
        description="Late fee correction",
        reason="Late fee applied in error",
        due_date=TODAY - dt.timedelta(days=8),
    )


def a_charge_with_a_pending_payment(lease):
    make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    make_payment(
        lease,
        amount=ONE_THOUSAND,
        payment_date=TODAY,
        status=PaymentStatus.PENDING,
        method="CHECK",
    )


def a_charge_with_a_void_payment(lease):
    make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    make_payment(
        lease,
        amount=ONE_THOUSAND,
        payment_date=TODAY,
        status=PaymentStatus.VOID,
        method="CHECK",
    )


def a_reversed_payment(lease):
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    payment = ledger_services.record_payment(
        lease, amount=ONE_THOUSAND, payment_date=TODAY - dt.timedelta(days=5), method="CHECK"
    )
    ledger_services.reverse_payment(payment, reason="the cheque bounced")
    return charge


def two_charges_one_partly_paid(lease):
    make_charge(
        lease,
        amount=Decimal("800.00"),
        due_date=TODAY - dt.timedelta(days=40),
        description="September",
    )
    make_charge(
        lease,
        amount=Decimal("900.00"),
        due_date=TODAY - dt.timedelta(days=5),
        description="October",
    )
    ledger_services.record_payment(
        lease, amount=Decimal("1000.00"), payment_date=TODAY - dt.timedelta(days=2), method="CHECK"
    )


def a_credit_on_the_account(lease):
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=10))
    ledger_services.record_payment(
        lease, amount=Decimal("500.00"), payment_date=TODAY - dt.timedelta(days=5), method="CHECK"
    )


SHAPES = [
    ("nothing at all", lambda lease: None),
    ("a charge", a_charge_only),
    ("a charge partly paid", a_charge_partly_paid),
    ("a charge paid", a_charge_paid),
    ("a charge reduced", a_charge_reduced),
    ("a charge reduced to nothing", a_charge_reduced_to_nothing),
    ("a charge increased", a_charge_increased),
    ("a paid charge increased", a_paid_charge_increased),
    ("a charge reduced then increased", a_charge_reduced_then_increased),
    ("a charge and a standalone entry", a_charge_and_a_standalone_entry),
    ("a charge with a pending payment", a_charge_with_a_pending_payment),
    ("a charge with a void payment", a_charge_with_a_void_payment),
    ("a reversed payment", a_reversed_payment),
    ("two charges, one partly paid", two_charges_one_partly_paid),
    ("a credit on the account", a_credit_on_the_account),
]


@pytest.mark.parametrize("description,shape", SHAPES, ids=[name for name, _ in SHAPES])
def test_the_balance_is_what_the_rows_add_up_to(description, shape):
    lease = a_tenancy()
    shape(lease)

    ledger = ledger_services.build_ledger(lease)

    assert ledger.balance_due == visible_total(ledger), (
        f"{description}: the account says {ledger.balance_due} but its rows add up to "
        f"{visible_total(ledger)}"
    )


# --- A1: a correction corrects a charge, not another correction -------------


def test_an_adjustment_cannot_be_adjusted_in_the_service():
    lease = a_tenancy()
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    correction = ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=ONE_THOUSAND, reason="not owed"
    )

    with pytest.raises(ValidationError, match="cannot itself be adjusted"):
        ledger_services.create_adjustment(
            correction, direction=Direction.INCREASE, amount=ONE_THOUSAND, reason="put it back"
        )

    assert ledger_services.build_ledger(lease).balance_due == Decimal("0.00")


def test_the_adjust_screen_refuses_an_adjustment_as_its_target():
    """The hole was reachable by a direct POST, so the screen must refuse it too."""
    lease = a_tenancy()
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    correction = ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=ONE_THOUSAND, reason="not owed"
    )
    client = make_admin(username="adjust-admin")
    desk = _signed_in(client)
    url = reverse("ledger:charge-adjust", args=[correction.pk])

    assert desk.get(url).status_code == 404
    assert (
        desk.post(
            url,
            {"direction": Direction.INCREASE, "amount": "1000.00", "reason": "put it back"},
        ).status_code
        == 404
    )
    assert ledger_services.build_ledger(lease).balance_due == Decimal("0.00")


def test_putting_a_reduction_back_is_done_on_the_original_charge():
    """What the refused path was being used for has a correct, visible way to do it."""
    lease = a_tenancy()
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=ONE_THOUSAND, reason="not owed"
    )

    ledger_services.create_adjustment(
        charge, direction=Direction.INCREASE, amount=ONE_THOUSAND, reason="it was owed after all"
    )

    ledger = ledger_services.build_ledger(lease)
    assert ledger.balance_due == ONE_THOUSAND
    assert ledger.balance_due == visible_total(ledger)
    row = next(row for row in ledger.transactions if row.charge_entry is not None)
    assert len(row.adjustments) == 2, "both corrections sit under the charge they correct"


# --- A2: a corrected charge reports the corrected figure --------------------


def test_an_increase_on_a_paid_charge_reads_as_arrears():
    lease = a_tenancy()
    a_paid_charge_increased(lease)

    ledger = ledger_services.build_ledger(lease)
    row = next(row for row in ledger.transactions if row.charge_entry is not None)

    assert ledger.balance_due == Decimal("200.00")
    assert ledger.arrears == Decimal("200.00")
    assert ledger.transactions[-1].running_balance == Decimal("200.00"), "the account closes at 200"
    assert row.status == "Past due", "the row said Paid while the account was in arrears"


def test_a_reduced_charge_still_reads_as_adjusted():
    lease = a_tenancy()
    a_charge_reduced_to_nothing(lease)

    ledger = ledger_services.build_ledger(lease)
    row = next(row for row in ledger.transactions if row.charge_entry is not None)

    assert ledger.balance_due == Decimal("0.00")
    assert row.status == "Adjusted"


def test_a_correction_is_never_counted_as_money_paid():
    lease = a_tenancy()
    charge = make_charge(lease, amount=ONE_THOUSAND, due_date=TODAY - dt.timedelta(days=10))
    ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("400.00"), reason="agreed"
    )
    ledger_services.record_payment(
        lease, amount=Decimal("600.00"), payment_date=TODAY - dt.timedelta(days=5), method="CHECK"
    )

    row = next(row for row in ledger_services.build_ledger(lease).statement if row.kind == "charge")

    assert row.gross == ONE_THOUSAND
    assert row.net == Decimal("600.00")
    assert row.paid == Decimal("600.00"), "only the money is money"
    assert row.left == Decimal("0.00")


def test_the_row_and_the_month_agree_about_a_corrected_charge():
    lease = a_tenancy()
    a_paid_charge_increased(lease)

    ledger = ledger_services.build_ledger(lease)
    row = next(row for row in ledger.transactions if row.charge_entry is not None)
    month_row = next(
        component.component
        for month in ledger.statement_months()
        if hasattr(month, "rows")
        for component in month.rows
        if component.component.kind == "charge"
    )

    assert row.status == month_row.state_label
    assert month_row.left == Decimal("200.00")


def _signed_in(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client
