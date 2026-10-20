"""Bills are a reading of immutable charges, not another financial record."""

import datetime as dt
import re
from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.leases.models import LeaseAccountStatus, LeaseStatus
from apps.ledger import services
from apps.ledger.models import ChargeKind, Direction, PaymentStatus
from apps.ledger.presentation import bill_history, transaction_history
from tests.factories import (
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_responsibility,
    make_tenant,
)

pytestmark = pytest.mark.django_db


def example_bill():
    tenant = make_tenant()
    lease = make_lease(
        tenants=[tenant], start_date=dt.date(2026, 1, 1), end_date=dt.date(2027, 12, 31)
    )
    due = dt.date(2026, 10, 5)
    for label, amount in (
        ("Gas", "33.20"),
        ("Electricity", "14.01"),
        ("Garbage", "9.83"),
        ("Water", "35.00"),
    ):
        expense = make_responsibility(lease.unit.property, label=label)
        make_charge(
            lease,
            due_date=due,
            amount=Decimal(amount),
            kind=ChargeKind.RESPONSIBILITY,
            responsibility=expense,
            description=f"{label} for October 2026",
        )
    make_charge(
        lease,
        due_date=due,
        amount=Decimal("305.52"),
        kind=ChargeKind.NNN,
        description="NNN for October 2026",
    )
    make_charge(lease, due_date=due, amount=Decimal("2113.00"), description="Rent for October 2026")
    return lease, tenant, due


def test_six_components_one_bill_payment_separate_and_no_writes(client):
    lease, tenant, due = example_bill()
    payment = make_payment(lease, amount=Decimal("1000"), payment_date=due)
    ledger = services.build_ledger(lease)
    bills = bill_history(ledger, newest=True)
    assert len(bills) == 2
    bill = bills[0]
    assert bill.total == Decimal("2510.56")
    assert bill.left == Decimal("1510.56")
    assert bill.paid == Decimal("1000")
    assert "Partly paid" in bill.state_label
    assert len(bill.rows) == len(bill.transactions) == 6
    assert bills[1].payment_entry == payment
    assert bill.running_balance == Decimal("2510.56")
    assert bills[1].running_balance == ledger.balance_due == Decimal("1510.56")
    client.force_login(make_manager())
    for route in ("leases:lease-detail", "ledger:lease-ledger"):
        response = client.get(reverse(route, args=[lease.pk]))
        html = response.content.decode()
        assert "October 5th 2026 Bill" in html
        assert html.count("data-bill-card") == 1
        summary = re.search(r'<summary class="bill-summary".*?</summary>', html, re.S)[0]
        assert "$2,510.56" in summary and "$1,510.56" in summary
        assert "Adjust" not in summary
        assert len(re.findall(r">Adjust</a>", html)) == 6
        breakdown = html.split('class="bill-breakdown"', 1)[1].split("</details>", 1)[0]
        assert "Paid" not in breakdown and "Remaining" not in breakdown
        assert "to pay" not in breakdown
        assert 'data-financial-icon="rent"' in breakdown
        assert 'data-financial-icon="recovery"' in breakdown
        assert html.index("</details>") < html.index('class="financial-payment"')
    client.force_login(tenant)
    for route in ("payments:home", "tenancy:lease", "accounts:home"):
        html = client.get(reverse(route)).content.decode()
        assert "October 5th 2026 Bill" in html
        assert "Payment received by RHP" in html
        breakdown = html.split('class="bill-breakdown"', 1)[1].split("</details>", 1)[0]
        assert "to pay" not in breakdown and "Remaining" not in breakdown
        assert ">Adjust</a>" not in html
    assert lease.charges.count() == 6 and lease.payments.count() == 1


def test_same_due_date_manual_charge_joins_bill_other_dates_stay_separate():
    lease, _tenant, due = example_bill()
    make_charge(lease, amount=Decimal("25"), due_date=due, kind=ChargeKind.MANUAL)
    make_charge(lease, amount=Decimal("50"), due_date=due + dt.timedelta(days=1))
    rows = bill_history(services.build_ledger(lease))
    assert len(rows) == 2
    assert rows[0].total == Decimal("2535.56") and len(rows[0].rows) == 7
    assert rows[1].total == Decimal("50")
    assert rows[-1].running_balance == Decimal("2585.56")


@pytest.mark.parametrize("scenario", ["pending", "paid", "mixed", "zero", "credit", "reversed"])
def test_bill_progress_and_corrections_are_aggregate_not_component_states(scenario):
    lease = make_lease()
    due = timezone.localdate() - dt.timedelta(days=1)
    charge = make_charge(lease, amount=Decimal("100"), due_date=due)
    make_charge(lease, kind=ChargeKind.MANUAL, amount=Decimal("100"), due_date=due)
    if scenario == "pending":
        make_payment(lease, amount=Decimal("200"), status=PaymentStatus.PENDING)
    elif scenario in ("paid", "mixed", "reversed"):
        payment = make_payment(lease, amount=Decimal("200" if scenario != "mixed" else "100"))
        if scenario == "reversed":
            services.reverse_payment(payment, reason="Mistaken receipt")
    else:
        services.create_adjustment(
            charge,
            amount=Decimal("100"),
            direction=Direction.DECREASE,
            reason="Internal correction",
        )
        other = lease.charges.filter(kind=ChargeKind.MANUAL).get()
        services.create_adjustment(
            other,
            amount=Decimal("100" if scenario == "zero" else "150"),
            direction=Direction.DECREASE,
            reason="Private reason",
        )
    ledger = services.build_ledger(lease)
    bill = next(row for row in bill_history(ledger) if isinstance(row, services.StatementMonth))
    if scenario == "pending":
        assert bill.left == Decimal("200") and bill.paid == 0 and bill.pending == Decimal("200")
        assert bill.state_label == "Payment pending"
    elif scenario == "paid":
        assert bill.left == 0 and bill.state_label == "Paid in full"
    elif scenario == "mixed":
        assert bill.left == Decimal("100") and bill.state_label == "Partly paid · Past due"
    elif scenario == "reversed":
        assert bill.left == Decimal("200") and bill.paid == 0
    else:
        assert bill.total == (Decimal("-50") if scenario == "credit" else 0)
        assert bill.left == 0 and bill.paid == 0
    html = render_to_string("components/statement_month.html", {"month": bill})
    assert "Internal correction" not in html and "Private reason" not in html
    breakdown = html.split('class="bill-breakdown"', 1)[1]
    assert "to pay" not in breakdown
    assert " open" not in html
    assert (
        sum(
            (
                row.total
                if isinstance(row, services.StatementMonth)
                else row.charge - row.payment_or_credit
                for row in bill_history(ledger)
            ),
            Decimal(0),
        )
        == ledger.balance_due
    )


def test_grouping_precedes_history_filter_and_preserves_balance_and_same_day_order():
    lease = make_lease()
    cutoff = transaction_history(services.build_ledger(lease))["transaction_cutoff"]
    make_charge(lease, amount=Decimal("200"), due_date=cutoff - dt.timedelta(days=1))
    # The payment can have been entered before the same-day charges: display remains bill first.
    make_payment(lease, amount=Decimal("50"), payment_date=cutoff)
    make_charge(lease, amount=Decimal("100"), due_date=cutoff)
    make_charge(lease, amount=Decimal("25"), due_date=cutoff, kind=ChargeKind.MANUAL)
    for sort in ("newest", "oldest"):
        result = transaction_history(services.build_ledger(lease), sort=sort)
        assert result["transaction_hidden_count"] == 1
        bill, payment = result["transaction_rows"]
        assert bill.total == Decimal("125") and len(bill.rows) == 2
        assert bill.running_balance == Decimal("325")
        assert payment.running_balance == Decimal("275")


def test_cancelled_expectation_remains_separate_and_settlement_hides_adjust(client):
    lease = make_lease(
        status=LeaseStatus.ENDED,
        account_status=LeaseAccountStatus.SETTLED,
        settled_at=timezone.now(),
    )
    make_charge(lease, amount=Decimal("50"))
    make_payment(lease, amount=Decimal("50"))
    make_payment(lease, amount=Decimal("25"), status=PaymentStatus.VOID)
    client.force_login(make_manager())
    html = client.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()
    assert "data-bill-card" in html
    assert ">Adjust</a>" not in html
    assert "Canceled expected payment" in html
    assert "Mark cleared" not in html
    assert "Remaining:" not in strip_tags(html)
