"""B3 bank registry, movements, CSV import and reconciliation."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounting import services
from apps.accounting.bank_csv import parse
from apps.accounting.models import BankAccount, StatementLine
from tests.factories import make_manager, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")
_counter = 0


def manager():
    global _counter
    _counter += 1
    return make_manager(username=f"bank-manager-{_counter}")


def bank():
    from apps.accounting.models import ChartAccount

    return BankAccount.objects.create(
        name="Operating",
        institution="Test Bank",
        last_four="1234",
        kind="OPERATING",
        chart_account=ChartAccount.objects.get(code="1110"),
    )


def test_a_bank_account_is_data_linked_to_one_chart_account():
    b = bank()
    assert b.chart_account.code == "1110"
    assert str(b) == "Operating · Test Bank (1234)"


def test_deposit_moves_undeposited_funds_into_the_bank():
    b = bank()
    movement = services.record_bank_movement(
        b, date=TODAY, kind="DEPOSIT", amount=Decimal("100.00"), actor=manager()
    )
    assert [
        (line.account.code, line.debit, line.credit)
        for line in movement.journal.lines.select_related("account").order_by("pk")
    ] == [
        ("1110", Decimal("100.00"), ZERO),
        ("1450", ZERO, Decimal("100.00")),
    ]


def test_csv_parser_reads_a_statement():
    rows = parse(
        "date,description,amount,reference\n"
        f"{TODAY.isoformat()},Rent deposit,100.00,ABC\n"
        f"{TODAY.isoformat()},Vendor payment,-25.00,\n"
    )
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("100.00")
    assert rows[1]["amount"] == Decimal("-25.00")


def test_import_matches_and_reconciles_a_statement():
    b = bank()
    services.record_bank_movement(
        b, date=TODAY, kind="DEPOSIT", amount=Decimal("100.00"), actor=manager()
    )
    statement = services.import_bank_statement(
        b,
        period_start=TODAY,
        period_end=TODAY,
        opening_balance=Decimal("0.00"),
        closing_balance=Decimal("100.00"),
        rows=[
            {
                "date": TODAY,
                "description": "Rent deposit",
                "amount": Decimal("100.00"),
                "reference": "ABC",
            }
        ],
        actor=manager(),
    )
    assert StatementLine.objects.get(statement=statement).matched_journal_line is not None
    reconciliation = services.reconcile_bank_statement(statement, actor=manager())
    assert reconciliation.difference == ZERO
    assert services.bank_control_tie(b)["difference"] == ZERO


def test_an_unmatched_statement_cannot_be_reconciled():
    b = bank()
    statement = services.import_bank_statement(
        b,
        period_start=TODAY,
        period_end=TODAY,
        opening_balance=Decimal("0.00"),
        closing_balance=Decimal("100.00"),
        rows=[
            {
                "date": TODAY,
                "description": "Missing movement",
                "amount": Decimal("100.00"),
                "reference": "",
            }
        ],
        actor=manager(),
    )
    with pytest.raises(ValidationError, match="Every statement line"):
        services.reconcile_bank_statement(statement, actor=manager())


def test_the_same_bank_period_cannot_be_imported_twice():
    b = bank()
    rows = [{"date": TODAY, "description": "x", "amount": Decimal("1.00"), "reference": ""}]
    services.import_bank_statement(
        b,
        period_start=TODAY,
        period_end=TODAY,
        opening_balance=Decimal("0.00"),
        closing_balance=Decimal("1.00"),
        rows=rows,
        actor=manager(),
    )
    with pytest.raises(ValidationError, match="already been imported"):
        services.import_bank_statement(
            b,
            period_start=TODAY,
            period_end=TODAY,
            opening_balance=Decimal("0.00"),
            closing_balance=Decimal("1.00"),
            rows=rows,
            actor=manager(),
        )


def test_manager_screens_and_tenant_refusal(client):
    manager_user = manager()
    client.force_login(manager_user)
    assert client.get(reverse("accounting:bank-list")).status_code == 200
    assert client.get(reverse("accounting:bank-create")).status_code == 200
    b = bank()
    assert client.get(reverse("accounting:bank-detail", args=[b.pk])).status_code == 200

    client.force_login(make_tenant(username="bank-outsider"))
    assert client.get(reverse("accounting:bank-list")).status_code == 403
    assert client.get(reverse("accounting:bank-detail", args=[b.pk])).status_code == 403
