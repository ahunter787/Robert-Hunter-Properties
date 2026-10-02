"""What a tenant sees of their own money, and nothing of anybody else's."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import PaymentStatus
from tests.factories import make_charge, make_lease, make_manager, make_payment, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def test_a_tenant_sees_their_balance_next_due_and_activity(client):
    tenant = make_tenant(username="ada", first_name="Ada")
    lease = make_lease(tenants=[tenant], monthly_rent=Decimal("1850.00"))
    make_charge(
        lease,
        amount=Decimal("1850.00"),
        due_date=TODAY,
        description="Rent for this month",
    )
    make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Your balance" in body
    assert "1,350.00" in body, "the balance shown is the derived one"
    assert "Next rent due" in body
    assert "Rent for this month" in body, "the activity list is real"
    assert "Payment received" in body


def test_a_tenant_paid_ahead_is_told_they_are_in_credit(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("300.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "in credit" in body
    assert "200.00" in body


def test_a_settled_tenancy_says_nothing_is_owing(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Settled" in body
    assert "nothing is owing" in body


def test_a_tenant_is_never_shown_another_tenancy_s_figures(client):
    """Two tenants, two leases: each page shows only its own numbers."""
    mine = make_tenant(username="ada", first_name="Ada")
    theirs = make_tenant(username="bob", first_name="Bob")
    my_lease = make_lease(tenants=[mine])
    their_lease = make_lease(tenants=[theirs])
    make_charge(my_lease, amount=Decimal("111.00"), due_date=TODAY, description="Mine only")
    make_charge(their_lease, amount=Decimal("999.00"), due_date=TODAY, description="Theirs only")

    client.force_login(mine)
    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Mine only" in body
    assert "Theirs only" not in body
    assert "999.00" not in body

    client.force_login(theirs)
    their_body = client.get(reverse("tenancy:lease")).content.decode()
    assert "Theirs only" in their_body
    assert "Mine only" not in their_body


def test_a_tenant_without_a_lease_gets_the_empty_page_not_a_ledger(client):
    tenant = make_tenant(username="newcomer")
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "No lease yet" in body
    assert "Your balance" not in body


def test_a_draft_lease_is_not_shown_to_its_tenant(client):
    """A tenancy that has not been activated is not a tenancy yet."""
    from apps.leases.models import LeaseStatus

    tenant = make_tenant(username="ada")
    make_lease(tenants=[tenant], status=LeaseStatus.DRAFT)
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "No lease yet" in body


def test_staff_are_turned_away_from_the_tenant_lease_page(client):
    client.force_login(make_manager(username="lease-manager"))

    assert client.get(reverse("tenancy:lease")).status_code == 403


def test_the_tenant_sees_an_expected_payment_as_pending_not_as_paid(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY, status=PaymentStatus.PENDING)
    client.force_login(tenant)

    ledger = services.build_ledger(lease)
    body = client.get(reverse("tenancy:lease")).content.decode()

    assert ledger.balance_due == Decimal("100.00")
    assert "100.00" in body, "the balance does not drop until the money is real"
    assert ledger.next_due.charge.pk == charge.pk


def test_a_voided_expected_payment_disappears_from_the_activity(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    payment = make_payment(
        lease,
        amount=Decimal("100.00"),
        payment_date=dt.date(2026, 1, 5),
        status=PaymentStatus.PENDING,
    )
    services.void_payment(payment, reason="never arrived")
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Payment received" not in body
