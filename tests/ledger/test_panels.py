"""The places money appears on screens that are not the ledger itself.

Two panels and a set of counters, all of which must agree with the ledger because
they read the same derived numbers.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from tests.factories import make_admin, make_charge, make_lease, make_manager, make_payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="panel-manager"))
    return client


def test_the_landing_page_shows_what_is_owed_and_what_is_late(signed_in):
    owing = make_lease()
    make_charge(owing, amount=Decimal("1000.00"), due_date=TODAY - dt.timedelta(days=5))
    make_payment(owing, amount=Decimal("250.00"), payment_date=TODAY)
    settled = make_lease()
    make_charge(settled, amount=Decimal("500.00"), due_date=TODAY)
    make_payment(settled, amount=Decimal("500.00"), payment_date=TODAY)

    response = signed_in.get(reverse("manage:home"))

    assert response.context["ledger_outstanding"] == Decimal("750.00")
    assert response.context["ledger_arrears"] == Decimal("750.00")
    assert response.context["ledger_arrears_leases"] == 1
    body = response.content.decode()
    assert "750.00" in body


def test_the_landing_page_counts_nothing_when_nothing_is_owed(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("500.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)

    response = signed_in.get(reverse("manage:home"))

    assert response.context["ledger_outstanding"] == Decimal("0.00")
    assert response.context["ledger_arrears_leases"] == 0


def test_a_draft_lease_is_not_counted_as_money(signed_in):
    from apps.leases.models import LeaseStatus

    make_lease(status=LeaseStatus.DRAFT)

    response = signed_in.get(reverse("manage:home"))

    assert response.context["ledger_outstanding"] == Decimal("0.00")


def test_the_lease_page_shows_the_ledger_panel(signed_in):
    lease = make_lease(monthly_rent=Decimal("1850.00"))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY, description="Rent for October")
    make_payment(lease, amount=Decimal("1850.00"), payment_date=TODAY)

    body = signed_in.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()

    assert "Ledger" in body
    assert "Settled" in body, "the panel states the derived balance"
    assert "Rent for October" in body, "recent activity is real"
    assert reverse("ledger:lease-ledger", args=[lease.pk]) in body


def test_the_lease_page_shows_an_outstanding_balance(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY - dt.timedelta(days=3))

    body = signed_in.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()

    assert "1,850.00" in body
    assert "past due" in body


def test_the_accounting_area_is_in_the_navigation_for_managers(signed_in):
    body = signed_in.get(reverse("manage:home")).content.decode()

    assert reverse("ledger:overview") in body


def test_a_maintenance_user_sees_no_accounting_navigation(client):
    from tests.factories import make_maintenance

    client.force_login(make_maintenance(username="maint"))
    body = client.get(reverse("manage:home")).content.decode()

    assert reverse("ledger:overview") not in body
    assert "ledger" not in body.lower() or "Accounting" not in body


def test_an_admin_sees_the_adjust_and_reverse_links(signed_in, client):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)

    manager_body = signed_in.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()
    assert reverse("ledger:charge-adjust", args=[charge.pk]) not in manager_body
    assert reverse("ledger:payment-reverse", args=[payment.pk]) not in manager_body

    client.force_login(make_admin(username="panel-admin"))
    admin_body = client.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()
    assert reverse("ledger:charge-adjust", args=[charge.pk]) in admin_body
    assert reverse("ledger:payment-reverse", args=[payment.pk]) in admin_body
