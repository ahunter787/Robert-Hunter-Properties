"""B5 closing, owner transactions and accountant exports."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import exports, services
from apps.accounting.models import BankAccount, ChartAccount, ExportBatch, JournalEntry
from apps.ledger.models import ChargeKind
from apps.ledger.services import create_charge
from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")
_counter = 0


def manager():
    global _counter
    _counter += 1
    return make_manager(username=f"b5-manager-{_counter}")


def bank():
    return BankAccount.objects.create(
        name="Operating",
        institution="Test Bank",
        last_four="1234",
        chart_account=ChartAccount.objects.get(code="1110"),
    )


def test_closing_moves_income_and_expense_to_equity():
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )
    services.record_vendor_bill(
        property=lease.unit.property,
        vendor=None,
        expense_account="5000",
        description="Repair",
        amount=Decimal("40.00"),
        received_on=TODAY,
        due_date=TODAY,
        actor=manager(),
    )

    journal = services.close_income_and_expense(as_of=TODAY, actor=manager())

    assert journal.event_type == "closing"
    accounts = {
        line.account.code: (line.debit, line.credit)
        for line in journal.lines.select_related("account")
    }
    assert accounts["4000"] == (Decimal("100.00"), ZERO)
    assert accounts["5000"] == (ZERO, Decimal("40.00"))
    assert accounts["3000"] == (ZERO, Decimal("60.00"))


def test_closing_is_idempotent():
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )
    first = services.close_income_and_expense(as_of=TODAY, actor=manager())
    second = services.close_income_and_expense(as_of=TODAY, actor=manager())
    assert first.pk == second.pk
    assert JournalEntry.objects.filter(event_type="closing").count() == 1


def test_owner_contributions_and_draws_post_against_equity():
    b = bank()
    contribution = services.record_owner_transaction(
        b, kind="CONTRIBUTION", amount=Decimal("1000.00"), date=TODAY, actor=manager()
    )
    assert [
        (line.account.code, line.debit, line.credit)
        for line in contribution.journal.lines.select_related("account").order_by("pk")
    ] == [
        ("1110", Decimal("1000.00"), ZERO),
        ("3100", ZERO, Decimal("1000.00")),
    ]
    draw = services.record_owner_transaction(
        b, kind="DRAW", amount=Decimal("200.00"), date=TODAY, actor=manager()
    )
    assert [
        (line.account.code, line.debit, line.credit)
        for line in draw.journal.lines.select_related("account").order_by("pk")
    ] == [
        ("3100", Decimal("200.00"), ZERO),
        ("1110", ZERO, Decimal("200.00")),
    ]


def test_journal_csv_and_text_exports_are_checksummed_and_audited():
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )
    csv_batch, csv_content = exports.create_journal_export(
        kind="JOURNAL_CSV", start=TODAY, end=TODAY, actor=manager()
    )
    text_batch, text_content = exports.create_journal_export(
        kind="JOURNAL_TEXT", start=TODAY, end=TODAY, actor=manager()
    )
    assert csv_batch.row_count == 2
    assert b"4000" in csv_content
    assert b"100.00" in csv_content
    assert b"4000" in text_content
    assert len(csv_batch.checksum) == 64
    assert csv_batch.checksum != text_batch.checksum
    assert ExportBatch.objects.count() == 2


def test_the_b5_screens_and_csv_download(client):
    b = bank()
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )
    client.force_login(manager())
    assert client.get(reverse("accounting:closing")).status_code == 200
    assert client.get(reverse("accounting:owner-list")).status_code == 200
    assert client.get(reverse("accounting:export-index")).status_code == 200
    csv_response = client.get(reverse("accounting:export-journal-csv"))
    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")
    assert len(csv_response["X-Export-Checksum"]) == 64
    text_response = client.get(reverse("accounting:export-journal-text"))
    assert text_response.status_code == 200
    assert text_response["Content-Type"].startswith("text/plain")
    assert b.pk


def test_tenants_cannot_reach_b5_actions(client):
    client.force_login(make_tenant(username="b5-outsider"))
    for name in ("closing", "owner-list", "export-index"):
        assert client.get(reverse(f"accounting:{name}")).status_code == 403
