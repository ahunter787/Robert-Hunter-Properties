"""Financial presentation is shared; authorization and money rules are unchanged."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import ChargeKind, Direction, PaymentStatus
from apps.ledger.presentation import financial_summary
from tests.factories import (
    make_charge,
    make_lease,
    make_maintenance,
    make_manager,
    make_payment,
    make_responsibility,
    make_tenant,
)


def test_financial_icons_use_money_and_task_symbols_not_file_actions():
    from apps.ledger.presentation import charge_icon

    assert charge_icon(ChargeKind.RENT) == "rent"
    assert charge_icon(ChargeKind.RESPONSIBILITY) == "recovery"
    assert charge_icon(ChargeKind.ADJUSTMENT) == "correction"
    assert charge_icon(ChargeKind.OPENING) == "starting"
    received = render_to_string("components/financial_icon.html", {"kind": "received"})
    rent = render_to_string("components/financial_icon.html", {"kind": "rent"})
    recovery = render_to_string("components/financial_icon.html", {"kind": "recovery"})
    assert '<rect x="2" y="3" width="18" height="12"' in received  # Banknote.
    assert "m4-4" not in received
    assert "M4 16v5h16v-5" not in received  # No download tray.
    assert "m3 10 9-7 9 7" in rent  # House roof, not a folded document.
    assert "M14 3v5h5" not in rent
    assert "M5 3h14v18" in recovery  # Receipt.
    for icon in (received, rent, recovery):
        assert 'aria-hidden="true"' in icon
        assert 'focusable="false"' in icon


def test_recovery_label_and_charge_icons_match_their_records_in_both_routes(client):
    client.force_login(make_manager())
    tenant = make_tenant()
    lease = lease_for_review(tenants=[tenant])
    expense = make_responsibility(lease.unit.property, label="Electricity")
    make_charge(
        lease,
        amount=Decimal("79"),
        kind=ChargeKind.RESPONSIBILITY,
        responsibility=expense,
        description="Electricity for October",
    )
    make_charge(lease, amount=Decimal("1850"), description="Rent for October")
    make_payment(lease, amount=Decimal("200"))
    for route in ("leases:lease-detail", "ledger:lease-ledger"):
        html = client.get(reverse(route, args=[lease.pk])).content.decode()
        assert "Expense Recovery" in html
        assert "Responsibility" not in html
        assert 'data-financial-icon="recovery"' in html
        assert 'data-financial-icon="rent"' in html
        assert 'data-financial-icon="received"' in html
    client.force_login(tenant)
    html = client.get(reverse("payments:home")).content.decode()
    assert "Electricity" in html
    assert "Responsibility" not in html
    assert 'data-financial-icon="recovery"' in html
    assert 'data-financial-icon="rent"' in html
    assert 'data-financial-icon="received"' in html


pytestmark = pytest.mark.django_db


def lease_for_review(**kwargs):
    today = timezone.localdate()
    return make_lease(
        start_date=today - timedelta(days=40), end_date=today + timedelta(days=400), **kwargs
    )


def test_both_entry_routes_have_identical_workspace_and_navigation(client):
    client.force_login(make_manager())
    lease = lease_for_review()
    make_charge(lease, amount=Decimal("840"), due_date=timezone.localdate() + timedelta(days=15))
    content = []
    for route in ("leases:lease-detail", "ledger:lease-ledger"):
        response = client.get(reverse(route, args=[lease.pk]), {"q": "Studio"})
        assert response.status_code == 200
        assert response.context["lease_section"] == "ledger"
        assert response.context["portal_active"] == "leases"
        assert b'aria-label="Lease sections"' in response.content
        assert b"Full-width ledger" not in response.content
        assert b"Unit workspace" not in response.content
        assert b"section=documents" in response.content
        assert b'class="lease-financial-history space-y-6"' in response.content
        assert b"q=Studio" in response.content
        content.append(
            re.sub(r'value="[A-Za-z0-9]{64}"', 'value="CSRF"', response.content.decode())
        )
    assert content[0] == content[1]
    response = client.get(reverse("ledger:lease-ledger", args=[lease.pk]), {"section": "terms"})
    assert response.context["lease_section"] == "ledger"


@pytest.mark.parametrize(
    "state", ["empty", "paid", "credit", "pending", "upcoming", "overdue", "corrected"]
)
def test_shared_summary_states_use_authoritative_amounts(state):
    lease = lease_for_review()
    today = timezone.localdate()
    if state == "credit":
        make_payment(lease, amount=Decimal("200"))
    elif state != "empty":
        charge = make_charge(
            lease,
            amount=Decimal("840"),
            due_date=today + timedelta(days=15)
            if state == "upcoming"
            else today - timedelta(days=1),
        )
        if state == "paid":
            make_payment(lease, amount=Decimal("840"))
        elif state == "pending":
            make_payment(lease, amount=Decimal("840"), status=PaymentStatus.PENDING)
        elif state == "corrected":
            services.create_adjustment(
                charge,
                direction=Direction.DECREASE,
                amount=Decimal("40"),
                reason="Synthetic correction",
            )
    ledger = services.build_ledger(lease)
    summary = financial_summary(ledger)
    html = render_to_string("components/financial_summary.html", summary)
    if state == "empty":
        assert "No charges or payments recorded" in html
        assert "Paid in full" not in html
    elif state == "paid":
        assert "Paid in full" in html
    elif state == "credit":
        assert "Credit balance" in html
        assert 'money-received">$200.00</dd>' in html
    elif state == "upcoming":
        assert ledger.due_now == 0
        assert ledger.not_yet_due == Decimal("840")
        assert html.count('money-owed">$840.00</dd>') == 2
        assert "Includes upcoming charges" in html
    elif state == "pending":
        assert ledger.due_now == Decimal("840")
        assert "Paid in full" not in html
    elif state == "corrected":
        assert ledger.due_now == Decimal("800")
    else:
        assert ledger.arrears == Decimal("840")


def test_forecast_stays_black_and_is_not_reported_as_posted_debt():
    lease = lease_for_review()
    ledger = services.build_ledger(lease)
    summary = financial_summary(ledger)
    assert summary["scheduled_date"]
    assert ledger.not_yet_due == 0
    html = render_to_string("components/financial_summary.html", summary)
    assert "Next scheduled rent—not yet added" in html
    assert 'class="money-statement">$1,850.00</span>' in html
    # Even a paid/canceled posted rent period must not be advertised as unposted.
    make_charge(lease, due_date=summary["scheduled_date"], amount=Decimal("1850"))
    assert financial_summary(services.build_ledger(lease))["scheduled_date"] is None


def test_corrected_to_zero_is_not_evidence_of_payment():
    lease = lease_for_review()
    charge = make_charge(lease, amount=Decimal("50"))
    services.create_adjustment(
        charge, amount=Decimal("50"), direction=Direction.DECREASE, reason="Wrong charge"
    )
    assert not financial_summary(services.build_ledger(lease))["paid_in_full"]


def test_pending_and_corrections_have_amount_only_styles_in_both_portals(client):
    tenant = make_tenant()
    lease = lease_for_review(tenants=[tenant])
    charge = make_charge(lease, amount=Decimal("840"), kind=ChargeKind.MANUAL)
    services.create_adjustment(
        charge,
        amount=Decimal("40"),
        direction=Direction.DECREASE,
        reason="Staff-only correction reason",
    )
    make_payment(lease, amount=Decimal("75"), status=PaymentStatus.PENDING)
    client.force_login(make_manager())
    staff = client.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()
    assert 'class="money-change">$40.00</span>' in staff
    assert re.search(r'class="[^\"]*money-statement">\$75.00</p>', staff)
    assert "Expected—not received" in staff
    assert 'class="financial-icon" aria-hidden="true"' in staff
    client.force_login(tenant)
    tenant_html = client.get(reverse("payments:home")).content.decode()
    assert 'class="money-change">$40.00</span>' in tenant_html
    assert "Expected—not received" in tenant_html
    assert "Staff-only correction reason" not in tenant_html
    assert "Audit history" not in tenant_html
    assert "Mark cleared" not in tenant_html
    assert "text-warning" not in tenant_html


def test_green_credit_is_equivalent_in_tenant_lease_statement_and_dashboard(client):
    tenant = make_tenant()
    lease = lease_for_review(tenants=[tenant])
    make_payment(lease, amount=Decimal("200"))
    client.force_login(tenant)
    for route in ("tenancy:lease", "payments:home", "accounts:home"):
        response = client.get(reverse(route))
        assert response.status_code == 200
        assert b"Credit balance" in response.content
        assert re.search(r"money-received[^>]*>\$200\.00", response.content.decode())


@pytest.mark.parametrize("factory", [make_tenant, make_maintenance])
def test_shared_staff_routes_do_not_expand_access(client, factory):
    client.force_login(factory())
    lease = lease_for_review()
    for route in ("leases:lease-detail", "ledger:lease-ledger"):
        assert client.get(reverse(route, args=[lease.pk])).status_code == 403


def test_default_history_is_newest_first_and_keeps_full_history_balances(client):
    from apps.ledger.presentation import transaction_history

    client.force_login(make_manager())
    lease = lease_for_review()
    cutoff = transaction_history(services.build_ledger(lease))["transaction_cutoff"]
    old = make_charge(
        lease,
        amount=Decimal("200"),
        due_date=cutoff - timedelta(days=1),
        description="Older starting charge",
    )
    make_charge(lease, amount=Decimal("50"), due_date=cutoff, description="Boundary charge")
    make_charge(lease, amount=Decimal("100"), description="Recent charge")
    make_payment(lease, amount=Decimal("50"))
    make_payment(
        lease,
        amount=Decimal("75"),
        payment_date=timezone.localdate() + timedelta(days=5),
        status=PaymentStatus.PENDING,
    )
    from apps.ledger.presentation import bill_history

    complete = bill_history(services.build_ledger(lease))
    balances = {
        (row.date, getattr(row, "kind", "payment")): row.running_balance for row in complete
    }
    for route in ("leases:lease-detail", "ledger:lease-ledger"):
        response = client.get(reverse(route, args=[lease.pk]))
        rows = response.context["transaction_rows"]
        assert response.context["transaction_sort"] == "newest"
        assert response.context["transaction_history"] == "year"
        assert response.context["transaction_hidden_count"] == 1
        assert [row.date for row in rows] == sorted((row.date for row in rows), reverse=True)
        assert all(row.date != old.due_date for row in rows)
        assert all(
            row.running_balance == balances[(row.date, getattr(row, "kind", "payment"))]
            for row in rows
        )
        assert rows[0].running_balance == Decimal("300")
        assert "Show all history (1 older transaction)" in response.content.decode()
        all_history = client.get(
            reverse(route, args=[lease.pk]), {"history": "all", "sort": "oldest", "q": "Studio"}
        )
        assert len(all_history.context["transaction_rows"]) == 5
        assert all_history.context["transaction_rows"][0].transactions[0].charge_entry == old
        assert all(
            "history=all" in tab["url"] and "sort=oldest" in tab["url"] and "q=Studio" in tab["url"]
            for tab in all_history.context["lease_tabs"]
        )
    assert lease.charges.count() == 3
    assert lease.payments.count() == 2


def test_history_validation_and_empty_period_do_not_hide_the_account(client):
    from apps.ledger.presentation import transaction_history

    client.force_login(make_manager())
    lease = lease_for_review()
    cutoff = transaction_history(services.build_ledger(lease))["transaction_cutoff"]
    make_charge(lease, due_date=cutoff - timedelta(days=1), amount=Decimal("200"))
    response = client.get(
        reverse("ledger:lease-ledger", args=[lease.pk]),
        {"sort": "https://example.org/", "history": "wrong"},
    )
    assert response.context["transaction_rows"] == []
    assert response.context["transaction_sort"] == "newest"
    assert response.context["transaction_history"] == "year"
    assert response.context["ledger"].balance_due == Decimal("200")
    assert b"No transactions in this period" in response.content
    assert b"No charges or payments recorded" not in response.content
    assert b"example.org" not in response.content


def test_one_year_cutoff_handles_leap_day(monkeypatch):
    from datetime import date

    from apps.ledger.presentation import transaction_history

    monkeypatch.setattr(timezone, "localdate", lambda *args: date(2024, 2, 29))
    result = transaction_history(services.build_ledger(lease_for_review()))
    assert result["transaction_cutoff"] == date(2023, 2, 28)
