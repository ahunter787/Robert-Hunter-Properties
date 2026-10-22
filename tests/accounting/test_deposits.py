"""B2 deposit GL: money held and returned, with retention waiting for its E6 charge."""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import JournalEntry
from apps.leases import services as lease_services
from apps.ledger import deposits
from apps.ledger.models import ChargeKind, FundsApplication
from apps.ledger.services import create_charge
from tests.factories import make_lease, make_manager

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")


def manager():
    return make_manager(username=f"deposit-gl-{timezone.now().microsecond}")


def ended_lease(*, deposit="500.00"):
    lease = make_lease(
        start_date=TODAY - dt.timedelta(days=200),
        end_date=TODAY - dt.timedelta(days=20),
        deposit=Decimal(deposit),
    )
    deposits.record(
        lease,
        kind="RECEIVED",
        amount=Decimal(deposit),
        date=TODAY - dt.timedelta(days=200),
        actor=manager(),
    )
    lease_services.end_lease(
        lease,
        ended_on=TODAY - dt.timedelta(days=10),
        reason="END_OF_TERM",
        note="Term ran out",
        actor=manager(),
    )
    lease.refresh_from_db()
    return lease


def lines(entry):
    return [
        (line.account.code, line.debit, line.credit)
        for line in entry.lines.select_related("account").order_by("pk")
    ]


def test_deposit_received_posts_to_undeposited_funds_and_liability():
    lease = make_lease()
    entry = deposits.record(
        lease, kind="RECEIVED", amount=Decimal("500.00"), date=TODAY, actor=manager()
    )
    journal = JournalEntry.objects.get(source_key=f"deposit:{entry.pk}:received")
    assert lines(journal) == [
        ("1450", Decimal("500.00"), ZERO),
        ("2300", ZERO, Decimal("500.00")),
    ]
    assert services.deposit_control_tie()["difference"] == ZERO


def test_deposit_return_posts_out_of_the_liability():
    lease = ended_lease()
    returned = deposits.record(
        lease, kind="RETURNED", amount=Decimal("500.00"), date=TODAY, actor=manager()
    )
    journal = JournalEntry.objects.get(source_key=f"deposit:{returned.pk}:returned")
    assert lines(journal) == [
        ("2300", Decimal("500.00"), ZERO),
        ("1450", ZERO, Decimal("500.00")),
    ]
    assert services.deposit_control_tie()["difference"] == ZERO


def test_a_retention_posts_nothing_and_shows_as_a_pending_difference():
    lease = ended_lease()
    withheld = deposits.record(
        lease,
        kind="WITHHELD",
        amount=Decimal("300.00"),
        date=TODAY,
        reason="Cleaning",
        actor=manager(),
    )
    assert not JournalEntry.objects.filter(source_key=f"deposit:{withheld.pk}:withheld").exists()
    tie = services.deposit_control_tie()
    assert tie["control"] == Decimal("500.00")
    assert tie["register"] == Decimal("200.00")
    assert tie["difference"] == Decimal("300.00")


def test_a_retained_deposit_applied_to_an_existing_bill_moves_liability_to_ar():
    lease = make_lease(
        start_date=TODAY - dt.timedelta(days=200),
        end_date=TODAY - dt.timedelta(days=20),
        deposit=Decimal("500.00"),
    )
    rent = create_charge(
        lease,
        description="Arrears",
        amount=Decimal("300.00"),
        due_date=TODAY - dt.timedelta(days=30),
        kind=ChargeKind.MANUAL,
    )
    deposits.record(
        lease,
        kind="RECEIVED",
        amount=Decimal("500.00"),
        date=TODAY - dt.timedelta(days=200),
        actor=manager(),
    )
    lease_services.end_lease(
        lease,
        ended_on=TODAY - dt.timedelta(days=10),
        reason="END_OF_TERM",
        note="Term ran out",
        actor=manager(),
    )
    lease.refresh_from_db()
    withheld = deposits.record(
        lease,
        kind="WITHHELD",
        amount=Decimal("300.00"),
        date=TODAY,
        reason="Arrears",
        actor=manager(),
    )
    application = FundsApplication.objects.create(
        lease=lease,
        source_deposit=withheld,
        target=rent,
        amount=Decimal("300.00"),
        is_credit=True,
    )
    journal = JournalEntry.objects.get(source_key=f"application:{application.pk}:applied")
    assert lines(journal) == [
        ("2300", Decimal("300.00"), ZERO),
        ("1200", ZERO, Decimal("300.00")),
    ]
    assert services.ar_control_tie()["difference"] == ZERO
