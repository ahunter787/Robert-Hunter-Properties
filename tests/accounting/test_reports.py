"""B4 reports read the journal and tie back to it; CSV and manager access."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import reports, services
from apps.ledger.deposits import record as record_deposit
from apps.ledger.models import ChargeKind
from apps.ledger.services import create_charge
from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
_counter = 0


def manager():
    global _counter
    _counter += 1
    return make_manager(username=f"report-manager-{_counter}")


def lease_and_books():
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=TODAY - dt.timedelta(days=10),
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
    return lease


def test_income_statement_reads_income_and_expense_lines():
    lease_and_books()
    report = reports.income_statement(TODAY - dt.timedelta(days=30), TODAY)
    assert report["total_income"] == Decimal("100.00")
    assert report["total_expenses"] == Decimal("40.00")
    assert report["net"] == Decimal("60.00")


def test_balance_sheet_balances_with_current_earnings():
    lease_and_books()
    report = reports.balance_sheet(TODAY)
    assert report["total_assets"] == Decimal("100.00")
    assert report["total_liabilities"] == Decimal("40.00")
    assert report["total_equity"] == Decimal("60.00")
    assert report["balanced"] is True


def test_cash_flow_uses_bank_and_undeposited_funds():
    from apps.ledger.services import record_payment

    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("50.00"),
        due_date=TODAY,
        kind=ChargeKind.RENT,
    )
    record_payment(
        lease, amount=Decimal("50.00"), payment_date=TODAY, method="ACH", actor=manager()
    )
    report = reports.cash_flow(TODAY, TODAY)
    assert report["net"] == Decimal("50.00")
    assert report["closing"] == Decimal("50.00")


def test_schedule_e_groups_the_chart():
    lease_and_books()
    report = reports.schedule_e(TODAY - dt.timedelta(days=30), TODAY)
    lines = {row["line"]: row["amount"] for row in report["lines"]}
    assert lines["3"] == Decimal("100.00")
    assert lines["14"] == Decimal("40.00")
    assert report["net"] == Decimal("60.00")


def test_aging_and_deposit_register_read_the_subledgers():
    lease = lease_and_books()
    record_deposit(
        lease,
        kind="RECEIVED",
        amount=Decimal("500.00"),
        date=TODAY,
        actor=manager(),
    )
    ar = reports.ar_aging(TODAY)
    ap = reports.ap_aging(TODAY)
    deposits = reports.deposit_register(TODAY)
    assert ar["total"] == Decimal("100.00")
    assert ap["total"] == Decimal("40.00")
    assert deposits["total"] == Decimal("500.00")


def test_a_manager_reads_the_reports_and_csv(client):
    lease_and_books()
    client.force_login(manager())
    for name in (
        "report-index",
        "report-income",
        "report-balance-sheet",
        "report-cash-flow",
        "report-schedule-e",
        "report-ar-aging",
        "report-ap-aging",
        "report-deposits",
    ):
        response = client.get(reverse(f"accounting:{name}"))
        assert response.status_code == 200, name
    csv_response = client.get(reverse("accounting:report-income") + "?format=csv")
    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")


def test_tenants_cannot_read_reports(client):
    client.force_login(make_tenant(username="report-outsider"))
    for name in ("report-index", "report-income", "report-balance-sheet", "report-ar-aging"):
        assert client.get(reverse(f"accounting:{name}")).status_code == 403
