"""The tenant's own payment history at /payments/.

Read-only, session-scoped, and rendered as list rows rather than a table so it
reads on a phone. It shows the same derived figures as the office's ledger.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import strip_tags

from apps.ledger import services
from apps.ledger.models import Direction, PaymentStatus
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def payments():
    return reverse("payments:home")


@pytest.fixture
def in_early_october(monkeypatch):
    """The day the owner read the page and found the readout oppressive.

    The figures in the regression below are their own tenancy's, so this test is
    about a readout a person actually saw rather than an invented one (ADR-012).
    """
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *args: dt.date(2026, 10, 2))


def test_a_tenancy_three_months_behind_reads_plainly(client, payments, in_early_october):
    """What is due now, when the next rent is — not the whole term's balance."""
    tenant = make_tenant(username="ada")
    lease = make_lease(
        tenants=[tenant],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31),
        rent_due_day=5,
        monthly_rent=Decimal("2084.00"),
    )
    by_month = {}
    for month in range(1, 12):
        due = dt.date(2026, month, 5)
        by_month[month] = make_charge(
            lease,
            amount=Decimal("2084.00"),
            due_date=due,
            description=f"Rent for {due:%B %Y}",
        )
    for month in (1, 2):
        services.create_adjustment(
            by_month[month],
            direction=Direction.DECREASE,
            amount=Decimal("2084.00"),
            reason="tenant not in residence",
        )
    make_payment(lease, amount=Decimal("10000.00"), payment_date=dt.date(2026, 8, 6))
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(payments).content.decode()).split())

    assert "Due now $4,588.00" in body, "what the tenant has to find, not the lease total"
    assert f"$4,588.00 past due · since {date_format(dt.date(2026, 7, 5))}" in body
    assert f"Next rent due {date_format(dt.date(2026, 10, 5))}: $2,084.00." in body
    assert "$4,168.00 is billed but not yet due" in body
    assert "8,756.00" not in body, "the rest of the term is not a tenant's headline"
    assert "was $2,084.00, adjusted down by $2,084.00" in body, "the credited months read net"


def test_a_tenant_sees_what_they_were_charged_and_what_they_paid(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant], monthly_rent=Decimal("1850.00"))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY, description="Rent for October")
    make_payment(
        lease,
        amount=Decimal("1850.00"),
        payment_date=TODAY,
        external_reference="ACH-77",
    )
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Rent for October" in body
    assert "Paid" in body
    assert "Payment received" in body
    assert "ACH-77" in body
    assert "Nothing due" in body


def test_the_due_now_and_next_rent_match_the_ledger(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("250.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(payments).content.decode()
    ledger = services.build_ledger(lease)

    assert ledger.balance_due == Decimal("750.00")
    assert ledger.due_now == Decimal("750.00")
    assert "750.00" in body
    assert "Next rent due" in body


def test_a_partly_paid_charge_says_so(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("400.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Partly paid" in body
    assert "paid $400.00 of $1,000.00" in body, "the row states its own settlement"


def test_a_late_charge_is_flagged_as_past_due(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=5))
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Past due" in body
    assert "1,000.00 past due" in " ".join(body.split()), "the summary says how much is late"


def test_an_expected_payment_is_labelled_as_expected(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY, status=PaymentStatus.PENDING)
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Payment expected" in body
    assert "1,000.00" in body, "the balance does not drop for money that has not arrived"


def test_a_charge_adjusted_to_nothing_reads_that_way(client, payments):
    """The owner's case: charged 2,084, credited 2,084, and the tenant sees 0."""
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    charge = make_charge(lease, amount=Decimal("2084.00"), due_date=TODAY)
    services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("2084.00"), reason="raised in error"
    )
    client.force_login(tenant)

    body = " ".join(client.get(payments).content.decode().split())

    assert "was $2,084.00, adjusted down by $2,084.00" in body
    assert "Nothing to pay" in body
    assert "−$2,084.00" not in body, "no opposing pair for the tenant to reconcile"
    assert "Adjustment" not in body, "the correction is not its own entry here"


def test_an_adjustment_leaves_the_charge_costing_what_it_costs_now(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("250.00"), reason="overcharged"
    )
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "$750.00" in body
    assert "was $1,000.00" in body
    assert "−$250.00" not in body


def test_the_statement_is_one_list(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=30))
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Your statement" in body
    assert "What you were charged" not in body
    assert "What you paid" not in body
    assert "Payment received" in body, "payments are in the same list as charges"


def test_a_long_history_is_paginated(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    for index in range(25):
        make_charge(
            lease,
            amount=Decimal("100.00"),
            due_date=TODAY - dt.timedelta(days=30 * index),
            description=f"Rent {index:02d}",
        )
    client.force_login(tenant)

    first = client.get(payments)
    assert first.context["statement_total"] == 25
    assert len(first.context["statement"]) == 20
    assert first.context["page_obj"].has_next()

    second = client.get(payments, {"page": 2})
    assert len(second.context["statement"]) == 5

    # A stale link falls back rather than 404-ing.
    assert client.get(payments, {"page": 99}).status_code == 200
    assert client.get(payments, {"page": "nonsense"}).status_code == 200


def test_a_voided_payment_is_not_shown(client, payments):
    """Void rows are office bookkeeping, not the tenant's business."""
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    payment = make_payment(
        lease,
        amount=Decimal("1000.00"),
        payment_date=TODAY,
        status=PaymentStatus.PENDING,
        external_reference="VOID-ME",
    )
    services.void_payment(payment, reason="never arrived")
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "VOID-ME" not in body
    assert "Your charges and payments will appear here." in body


def test_a_reversal_is_shown_as_a_reversal(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)
    services.reverse_payment(payment, reason="recorded twice")
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "Payment reversed" in body
    assert "1,000.00" in body, "the charge is outstanding again"


def test_two_tenants_never_see_each_others_money(client, payments):
    mine = make_tenant(username="ada")
    theirs = make_tenant(username="bob")
    my_lease = make_lease(tenants=[mine])
    their_lease = make_lease(tenants=[theirs])
    make_charge(my_lease, amount=Decimal("111.00"), due_date=TODAY, description="Mine only")
    make_charge(their_lease, amount=Decimal("999.00"), due_date=TODAY, description="Theirs only")

    client.force_login(mine)
    body = client.get(payments).content.decode()
    assert "Mine only" in body
    assert "Theirs only" not in body
    assert "999.00" not in body

    client.force_login(theirs)
    their_body = client.get(payments).content.decode()
    assert "Theirs only" in their_body
    assert "Mine only" not in their_body


def test_a_tenant_with_no_lease_gets_an_explanation_not_a_404(client, payments):
    client.force_login(make_tenant(username="newcomer"))

    response = client.get(payments)

    assert response.status_code == 200
    assert b"No lease yet" in response.content


def test_a_draft_lease_is_not_shown(client, payments):
    from apps.leases.models import LeaseStatus

    tenant = make_tenant(username="ada")
    make_lease(tenants=[tenant], status=LeaseStatus.DRAFT)
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "No lease yet" in body


@pytest.mark.parametrize("maker", [make_manager, make_admin], ids=["manager", "admin"])
def test_staff_are_turned_away(client, payments, maker):
    client.force_login(maker(username="staff-member"))

    assert client.get(payments).status_code == 403


def test_anonymous_visitors_are_sent_to_sign_in(client, payments):
    response = client.get(payments)

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_there_is_no_id_in_a_tenant_payment_url():
    """Nothing to enumerate: the session decides whose money this is."""
    assert reverse("payments:home") == "/payments/"
    assert "<int:pk>" not in reverse("payments:home")


def test_the_page_is_built_for_a_phone(client, payments):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(payments).content.decode()

    assert "<table" not in body, "list rows, not a wide table"
    assert 'name="viewport"' in body
    assert "divide-y" in body, "the entries are stacked rows"


def test_the_payments_page_is_reachable_from_the_tenant_navigation(client, payments):
    tenant = make_tenant(username="ada")
    make_lease(make_unit(identifier="Storefront"), tenants=[tenant])
    client.force_login(tenant)

    body = client.get(reverse("accounts:home")).content.decode()

    assert reverse("payments:home") in body
    assert "Payments" in client.get(reverse("tenancy:lease")).content.decode()
