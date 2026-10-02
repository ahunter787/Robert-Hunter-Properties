"""The ledger's arithmetic: balances, allocation, states, and immutability.

These are the specification's FINANCIAL tests — balance calculations, partial
payments, reversals, overdue determination — plus the rules that make the ledger
trustworthy: entries are append-only, and nothing stores a balance.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.dates import due_date_in
from apps.ledger import services
from apps.ledger.models import Charge, ChargeKind, ChargeState, Direction, Payment, PaymentStatus
from tests.factories import make_charge, make_lease, make_payment, make_unit

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def ledger_for(lease):
    return services.build_ledger(lease)


def state_of(ledger, charge):
    return next(line.state for line in ledger.charges if line.charge.pk == charge.pk)


# --- balance --------------------------------------------------------------


def test_the_balance_is_the_charges_minus_the_payments():
    lease = make_lease(monthly_rent=Decimal("1850.00"))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1850.00"), payment_date=TODAY)

    assert ledger_for(lease).balance_due == Decimal("0.00")


def test_a_part_payment_leaves_the_rest_owing():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("400.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("600.00")
    assert state_of(ledger, charge) == ChargeState.PARTIAL
    assert ledger.charges[0].settled == Decimal("400.00")
    assert ledger.charges[0].outstanding == Decimal("600.00")


def test_a_full_payment_settles_the_charge():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("0.00")
    assert state_of(ledger, charge) == ChargeState.PAID
    assert ledger.next_due is None


def test_paying_more_than_is_owed_is_a_credit_not_a_negative_debt():
    lease = make_lease()
    make_charge(lease, amount=Decimal("500.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("600.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("-100.00")
    assert ledger.credit == Decimal("100.00")
    assert ledger.overdue_amount == Decimal("0.00")


def test_no_balance_is_ever_stored():
    """The balance is a function of the entries; there is no column for it."""
    field_names = {field.name for field in Charge._meta.fields} | {
        field.name for field in Payment._meta.fields
    }
    assert not {name for name in field_names if "balance" in name}


# --- allocation -----------------------------------------------------------


def test_a_payment_settles_the_oldest_charge_first():
    lease = make_lease()
    oldest = make_charge(
        lease, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=60), description="Old"
    )
    newest = make_charge(
        lease, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=30), description="New"
    )
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert ledger.charges[0].charge.pk == oldest.pk, "charges are shown oldest first"
    assert state_of(ledger, oldest) == ChargeState.PAID
    assert state_of(ledger, newest) in (ChargeState.UNPAID, ChargeState.OVERDUE)


def test_two_part_payments_add_up_across_charges():
    lease = make_lease()
    first = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=30))
    second = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1500.00"), payment_date=TODAY)

    ledger = ledger_for(lease)
    assert state_of(ledger, first) == ChargeState.PAID
    assert state_of(ledger, second) == ChargeState.PARTIAL
    assert ledger.balance_due == Decimal("500.00")


# --- pending and void ----------------------------------------------------


def test_a_pending_payment_does_not_move_the_balance_but_marks_the_charge():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=5))
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY, status=PaymentStatus.PENDING)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("1000.00"), "pending money is not money yet"
    assert state_of(ledger, charge) == ChargeState.PENDING


def test_a_cleared_payment_then_counts():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(
        lease, amount=Decimal("1000.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )
    services.clear_payment(payment)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("0.00")
    assert state_of(ledger, charge) == ChargeState.PAID


def test_a_void_payment_counts_for_nothing():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(
        lease, amount=Decimal("1000.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )
    services.void_payment(payment)

    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("1000.00")
    assert state_of(ledger, charge) == ChargeState.UNPAID
    assert ledger.pending_payments == []


# --- reversals -----------------------------------------------------------


def test_reversing_a_payment_restores_the_balance_and_keeps_the_original():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)
    assert ledger_for(lease).balance_due == Decimal("0.00")

    reversal = services.reverse_payment(payment, reason="check bounced")

    payment.refresh_from_db()
    ledger = ledger_for(lease)
    assert ledger.balance_due == Decimal("1000.00")
    assert state_of(ledger, charge) == ChargeState.UNPAID
    assert Payment.objects.count() == 2, "the original and the reversal are both on the ledger"
    assert reversal.reverses_id == payment.pk
    assert payment.amount == Decimal("1000.00"), "the original is not edited"
    assert payment.is_reversed() is True


def test_a_payment_can_only_be_reversed_once():
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    services.reverse_payment(payment, reason="mistake")

    with pytest.raises(ValidationError):
        services.reverse_payment(payment, reason="again")


def test_a_pending_payment_cannot_be_reversed():
    lease = make_lease()
    payment = make_payment(
        lease, amount=Decimal("500.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )

    with pytest.raises(ValidationError):
        services.reverse_payment(payment, reason="not yet")


def test_a_reversal_is_not_itself_reversible():
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    reversal = services.reverse_payment(payment, reason="mistake")

    with pytest.raises(ValidationError):
        services.reverse_payment(reversal, reason="undo the undo")


def test_clearing_and_voiding_only_apply_to_a_pending_payment():
    lease = make_lease()
    cleared = make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    with pytest.raises(ValidationError):
        services.clear_payment(cleared)
    with pytest.raises(ValidationError):
        services.void_payment(cleared)


# --- adjustments ---------------------------------------------------------


def test_a_reducing_adjustment_lowers_the_balance_but_not_the_charge():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("250.00"), reason="overcharged"
    )

    charge.refresh_from_db()
    ledger = ledger_for(lease)
    assert charge.amount == Decimal("1000.00"), "the original charge is untouched"
    assert ledger.balance_due == Decimal("750.00")


def test_an_adjustment_needs_a_reason():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    adjustment = Charge(
        lease=lease,
        kind=ChargeKind.ADJUSTMENT,
        direction=Direction.DECREASE,
        description="Adjustment",
        amount=Decimal("10.00"),
        due_date=TODAY,
        adjusts=charge,
    )
    with pytest.raises(ValidationError):
        adjustment.save()


def test_a_reduction_must_say_which_charge_it_corrects():
    lease = make_lease()
    adjustment = Charge(
        lease=lease,
        kind=ChargeKind.ADJUSTMENT,
        direction=Direction.DECREASE,
        description="Adjustment",
        amount=Decimal("10.00"),
        due_date=TODAY,
        reason="goodwill",
    )
    with pytest.raises(ValidationError):
        adjustment.save()


# --- immutability --------------------------------------------------------


def test_a_charge_is_never_edited():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    charge.amount = Decimal("1.00")
    with pytest.raises(ValidationError, match="never edited"):
        charge.save()

    charge.refresh_from_db()
    assert charge.amount == Decimal("1000.00")


def test_a_charge_is_never_deleted():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    with pytest.raises(ValidationError, match="never deleted"):
        charge.delete()
    assert Charge.objects.filter(pk=charge.pk).exists()


def test_a_payment_is_never_edited():
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    payment.amount = Decimal("1.00")
    with pytest.raises(ValidationError, match="never edited"):
        payment.save()

    payment.refresh_from_db()
    assert payment.amount == Decimal("1000.00")


def test_a_payment_is_never_deleted():
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    with pytest.raises(ValidationError, match="never deleted"):
        payment.delete()
    assert Payment.objects.filter(pk=payment.pk).exists()


def test_a_status_can_only_move_from_pending():
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)

    payment.status = PaymentStatus.VOID
    with pytest.raises(ValidationError, match="only moves from pending"):
        payment.save()


def test_a_ledger_entry_cannot_be_attached_to_a_draft_lease():
    from apps.leases.models import LeaseStatus

    lease = make_lease(status=LeaseStatus.DRAFT)

    with pytest.raises(ValidationError, match="draft lease"):
        Charge.objects.create(
            lease=lease,
            kind=ChargeKind.MANUAL,
            description="Nope",
            amount=Decimal("10.00"),
            due_date=TODAY,
        )


# --- the database's own rules --------------------------------------------


def test_one_rent_charge_per_month_is_a_database_rule():
    lease = make_lease()
    make_charge(lease, kind=ChargeKind.RENT, due_date=dt.date(2026, 3, 1))

    with pytest.raises(IntegrityError), transaction.atomic():
        Charge.objects.create(
            lease=lease,
            kind=ChargeKind.RENT,
            description="Rent again",
            amount=Decimal("1850.00"),
            due_date=dt.date(2026, 3, 1),
        )


def test_a_rent_charge_cannot_reduce_what_is_owed():
    lease = make_lease()
    with pytest.raises(IntegrityError), transaction.atomic():
        Charge.objects.create(
            lease=lease,
            kind=ChargeKind.RENT,
            direction=Direction.DECREASE,
            description="Rent credit",
            amount=Decimal("10.00"),
            due_date=TODAY,
        )


def test_an_amount_must_be_at_least_a_cent():
    lease = make_lease()
    with pytest.raises(ValidationError):
        make_charge(lease, amount=Decimal("0.00"), due_date=TODAY)


# --- dates ---------------------------------------------------------------


def test_a_due_day_of_the_31st_clamps_to_the_end_of_a_short_month():
    assert due_date_in(2026, 2, 31) == dt.date(2026, 2, 28)
    assert due_date_in(2028, 2, 31) == dt.date(2028, 2, 29), "leap year"
    assert due_date_in(2026, 4, 31) == dt.date(2026, 4, 30)
    assert due_date_in(2026, 1, 31) == dt.date(2026, 1, 31)


def test_rent_dates_run_from_the_first_due_date_through_the_horizon():
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 12, 31), rent_due_day=1
    )

    dates = services.rent_due_dates(lease, through=dt.date(2026, 3, 31))

    assert dates == [dt.date(2026, 1, 1), dt.date(2026, 2, 1), dt.date(2026, 3, 1)]


def test_rent_dates_never_run_past_the_end_of_the_lease():
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 2, 15), rent_due_day=1
    )

    dates = services.rent_due_dates(lease, through=dt.date(2026, 12, 31))

    assert dates == [dt.date(2026, 1, 1), dt.date(2026, 2, 1)]


def test_a_tenancy_starting_after_its_due_day_is_not_charged_for_that_month():
    """Proration is out of scope: the desk adds a manual charge for a part month."""
    lease = make_lease(
        start_date=dt.date(2026, 1, 15), end_date=dt.date(2026, 12, 31), rent_due_day=1
    )

    dates = services.rent_due_dates(lease, through=dt.date(2026, 2, 28))

    assert dates == [dt.date(2026, 2, 1)]


def test_the_rent_due_day_is_clamped_when_it_is_generated():
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 12, 31), rent_due_day=31
    )

    dates = services.rent_due_dates(lease, through=dt.date(2026, 4, 30))

    assert dates == [
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 31),
        dt.date(2026, 4, 30),
    ]


# --- generation ----------------------------------------------------------


def test_generating_rent_charges_creates_one_per_month():
    lease = make_lease(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31),
        monthly_rent=Decimal("1850.00"),
        rent_due_day=1,
    )

    created = services.generate_rent_charges(lease, through=dt.date(2026, 3, 31))

    assert len(created) == 3
    assert Charge.objects.filter(lease=lease).count() == 3
    assert all(charge.kind == ChargeKind.RENT for charge in created)
    assert services.build_ledger(lease).balance_due == Decimal("5550.00")


def test_generating_rent_charges_twice_changes_nothing():
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 12, 31), rent_due_day=1
    )
    services.generate_rent_charges(lease, through=dt.date(2026, 3, 31))

    again = services.generate_rent_charges(lease, through=dt.date(2026, 3, 31))

    assert again == []
    assert Charge.objects.filter(lease=lease).count() == 3


def test_generating_rent_charges_on_a_draft_is_refused():
    from apps.leases.models import LeaseStatus

    lease = make_lease(status=LeaseStatus.DRAFT)

    with pytest.raises(ValidationError, match="draft lease"):
        services.generate_rent_charges(lease, through=TODAY)


def test_the_horizon_is_the_end_of_a_later_month():
    assert services.generation_horizon(0, today=dt.date(2026, 1, 15)) == dt.date(2026, 1, 31)
    assert services.generation_horizon(1, today=dt.date(2026, 1, 15)) == dt.date(2026, 2, 28)
    assert services.generation_horizon(2, today=dt.date(2026, 12, 5)) == dt.date(2027, 2, 28)


def test_a_lease_with_nothing_on_it_has_a_settled_ledger():
    lease = make_lease()

    ledger = ledger_for(lease)

    assert ledger.balance_due == Decimal("0.00")
    assert ledger.overdue_amount == Decimal("0.00")
    assert ledger.next_due is None
    assert ledger.activity == []


def test_an_out_of_service_unit_still_has_a_ledger():
    lease = make_lease(make_unit(is_active=False))
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)

    assert ledger_for(lease).balance_due == Decimal("100.00")
