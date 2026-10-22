"""B1 posting: balanced, sourced, immutable, idempotent and tied to the tenant ledger."""

import itertools
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import ChartAccount, JournalEntry
from apps.ledger.applications import release
from apps.ledger.models import (
    Charge,
    ChargeKind,
    Direction,
    FundsApplication,
    PaymentStatus,
)
from apps.ledger.services import (
    create_adjustment,
    create_charge,
    record_payment,
    reverse_payment,
)
from tests.factories import make_lease, make_manager, make_responsibility

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")


_MANAGERS = itertools.count(1)


def manager():
    return make_manager(username=f"accounting-manager-{next(_MANAGERS)}")


def entry_for(key):
    return JournalEntry.objects.get(source_key=key)


def lines(entry):
    return list(entry.lines.select_related("account").order_by("pk"))


def test_a_charge_posts_balanced_ar_and_income():
    lease = make_lease()
    charge = create_charge(
        lease,
        description="Rent",
        amount=Decimal("1850.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )

    entry = entry_for(f"charge:{charge.pk}:created")
    assert entry.event_type == "charge.rent"
    assert entry.lease == lease
    assert entry.property == lease.unit.property
    assert [(line.account.code, line.debit, line.credit) for line in lines(entry)] == [
        ("1200", Decimal("1850.00"), ZERO),
        ("4000", ZERO, Decimal("1850.00")),
    ]
    assert sum(line.debit for line in lines(entry)) == sum(line.credit for line in lines(entry))


def test_charge_kinds_use_their_mapped_income_accounts():
    lease = make_lease()
    responsibility = make_responsibility(property_obj=lease.unit.property, category="MAINTENANCE")
    create_charge(
        lease, description="NNN", amount=Decimal("10.00"), due_date=TODAY, kind=ChargeKind.NNN
    )
    water = Charge.objects.create(
        lease=lease,
        description="Water",
        amount=Decimal("20.00"),
        due_date=TODAY,
        kind=ChargeKind.RESPONSIBILITY,
        responsibility=responsibility,
    )
    services.post_charge(water)

    credit_codes = {
        line.account.code
        for entry in JournalEntry.objects.filter(lease=lease)
        for line in lines(entry)
        if line.credit
    }
    assert {"4100", "4300"} <= credit_codes


def test_an_adjustment_reverses_the_original_income():
    lease = make_lease()
    charge = create_charge(
        lease, description="Rent", amount=Decimal("1000.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    adjustment = create_adjustment(
        charge,
        direction=Direction.DECREASE,
        amount=Decimal("200.00"),
        reason="Correction",
        actor=manager(),
    )

    entry = entry_for(f"charge:{adjustment.pk}:created")
    assert [(line.account.code, line.debit, line.credit) for line in lines(entry)] == [
        ("4000", Decimal("200.00"), ZERO),
        ("1200", ZERO, Decimal("200.00")),
    ]
    assert services.account_balance("1200") == Decimal("800.00")


def test_opening_debt_and_credit_have_their_own_counterparts():
    lease = make_lease()
    debt = create_charge(
        lease,
        description="Brought forward",
        amount=Decimal("500.00"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        opening=True,
    )
    credit = create_charge(
        lease,
        description="Brought forward credit",
        amount=Decimal("300.00"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        opening=True,
        direction=Direction.DECREASE,
    )

    debt_entry = entry_for(f"charge:{debt.pk}:created")
    credit_entry = entry_for(f"charge:{credit.pk}:created")
    assert [(line.account.code, line.debit, line.credit) for line in lines(debt_entry)] == [
        ("1200", Decimal("500.00"), ZERO),
        ("3070", ZERO, Decimal("500.00")),
    ]
    assert [(line.account.code, line.debit, line.credit) for line in lines(credit_entry)] == [
        ("3070", Decimal("300.00"), ZERO),
        ("2400", ZERO, Decimal("300.00")),
    ]


def test_a_payment_posts_to_undeposited_funds_and_reverses():
    lease = make_lease()
    create_charge(
        lease, description="Rent", amount=Decimal("500.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    payment = record_payment(
        lease,
        amount=Decimal("500.00"),
        payment_date=TODAY,
        method="ACH",
        status=PaymentStatus.CLEARED,
        actor=manager(),
    )
    receipt = entry_for(f"payment:{payment.pk}:recorded")
    assert [(line.account.code, line.debit, line.credit) for line in lines(receipt)] == [
        ("1450", Decimal("500.00"), ZERO),
        ("1200", ZERO, Decimal("500.00")),
    ]
    assert services.account_balance("1200") == ZERO

    reverse_payment(payment, reason="Returned", actor=manager())
    reversal = entry_for(f"payment:{payment.pk}:reversed")
    assert [(line.account.code, line.debit, line.credit) for line in lines(reversal)] == [
        ("1200", Decimal("500.00"), ZERO),
        ("1450", ZERO, Decimal("500.00")),
    ]
    assert services.account_balance("1200") == Decimal("500.00")
    assert services.account_balance("1450") == ZERO


def test_a_pending_payment_posts_nothing_until_it_clears():
    lease = make_lease()
    payment = record_payment(
        lease,
        amount=Decimal("500.00"),
        payment_date=TODAY,
        method="ACH",
        status=PaymentStatus.PENDING,
        actor=manager(),
    )
    assert not JournalEntry.objects.filter(lease=lease).exists()

    from apps.ledger.services import clear_payment

    clear_payment(payment)
    assert JournalEntry.objects.filter(source_key=f"payment:{payment.pk}:cleared").exists()
    assert not JournalEntry.objects.filter(source_key=f"payment:{payment.pk}:recorded").exists()


def test_replaying_the_same_source_event_creates_one_journal():
    lease = make_lease()
    charge = create_charge(
        lease, description="Rent", amount=Decimal("100.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    first = entry_for(f"charge:{charge.pk}:created")

    again = services.post_charge(charge)

    assert again.pk == first.pk
    assert JournalEntry.objects.filter(source_key=f"charge:{charge.pk}:created").count() == 1


def test_posted_journals_and_lines_are_immutable():
    lease = make_lease()
    charge = create_charge(
        lease, description="Rent", amount=Decimal("100.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    entry = entry_for(f"charge:{charge.pk}:created")
    entry.memo = "changed"
    with pytest.raises(ValidationError):
        entry.save()
    with pytest.raises(ValidationError):
        entry.delete()

    line = entry.lines.first()
    line.debit = Decimal("1.00")
    with pytest.raises(ValidationError):
        line.save()
    with pytest.raises(ValidationError):
        line.delete()


def test_manual_journals_cannot_touch_control_accounts():
    with pytest.raises(ValidationError, match="Control accounts"):
        services.post_manual_journal(
            source_key="manual:1:test",
            posted_on=TODAY,
            lines=[
                {"account": "1200", "debit": Decimal("1.00")},
                {"account": "3070", "credit": Decimal("1.00")},
            ],
            memo="bad",
            actor=manager(),
        )


def test_an_opening_credit_application_moves_2400_to_ar_and_ties():
    lease = make_lease()
    rent = create_charge(
        lease, description="Rent", amount=Decimal("1000.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    opening = create_charge(
        lease,
        description="Opening credit",
        amount=Decimal("400.00"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        opening=True,
        direction=Direction.DECREASE,
    )
    application = FundsApplication.objects.create(
        lease=lease, source_charge=opening, target=rent, amount=Decimal("400.00"), is_credit=True
    )

    entry = entry_for(f"application:{application.pk}:applied")
    assert [(line.account.code, line.debit, line.credit) for line in lines(entry)] == [
        ("2400", Decimal("400.00"), ZERO),
        ("1200", ZERO, Decimal("400.00")),
    ]
    tie = services.ar_control_tie()
    assert tie["difference"] == ZERO, tie


def test_a_released_opening_credit_reopens_2400_and_ties():
    lease = make_lease()
    rent = create_charge(
        lease, description="Rent", amount=Decimal("1000.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    opening = create_charge(
        lease,
        description="Opening credit",
        amount=Decimal("400.00"),
        due_date=TODAY,
        kind=ChargeKind.OPENING,
        opening=True,
        direction=Direction.DECREASE,
    )
    application = FundsApplication.objects.create(
        lease=lease, source_charge=opening, target=rent, amount=Decimal("400.00"), is_credit=True
    )
    release_row = release(application, reason="Wrong target", actor=manager())

    entry = entry_for(f"application:{release_row.pk}:released")
    assert [(line.account.code, line.debit, line.credit) for line in lines(entry)] == [
        ("1200", Decimal("400.00"), ZERO),
        ("2400", ZERO, Decimal("400.00")),
    ]
    assert services.ar_control_tie()["difference"] == ZERO


def test_receipt_applications_do_not_post_again():
    lease = make_lease()
    rent = create_charge(
        lease, description="Rent", amount=Decimal("300.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    payment = record_payment(
        lease, amount=Decimal("300.00"), payment_date=TODAY, method="ACH", actor=manager()
    )
    before = JournalEntry.objects.filter(lease=lease).count()
    FundsApplication.objects.create(
        lease=lease, source_payment=payment, target=rent, amount=Decimal("300.00")
    )
    assert JournalEntry.objects.filter(lease=lease).count() == before


def test_the_ar_control_ties_after_charges_adjustments_and_payments():
    lease = make_lease()
    charge = create_charge(
        lease, description="Rent", amount=Decimal("1000.00"), due_date=TODAY, kind=ChargeKind.RENT
    )
    create_adjustment(
        charge,
        direction=Direction.DECREASE,
        amount=Decimal("100.00"),
        reason="Correction",
        actor=manager(),
    )
    record_payment(
        lease, amount=Decimal("400.00"), payment_date=TODAY, method="ACH", actor=manager()
    )

    tie = services.ar_control_tie()
    assert tie["control"] == Decimal("500.00")
    assert tie["subledger"] == Decimal("500.00")
    assert tie["difference"] == ZERO

    rows = services.trial_balance()
    assert sum(row["debit"] for row in rows) == sum(row["credit"] for row in rows)


def test_the_chart_is_seeded_with_control_accounts():
    assert ChartAccount.objects.get(code="1200").is_control is True
    assert ChartAccount.objects.get(code="4000").kind == "INCOME"


def test_generated_scheduled_charges_post_to_the_gl():
    from apps.ledger.services import generate_charges

    lease = make_lease(start_date=TODAY.replace(day=1), monthly_rent=Decimal("1000.00"))
    created = generate_charges(lease, through=TODAY)

    assert created, "the fixture should raise at least one scheduled charge"
    for charge in created:
        assert JournalEntry.objects.filter(source_key=f"charge:{charge.pk}:created").exists()
    assert services.ar_control_tie()["difference"] == ZERO
