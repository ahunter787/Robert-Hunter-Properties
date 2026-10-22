"""Screens show what the lease charges *now*, not the rent it opened with.

A stepped or stated lease stores its starting rent in ``monthly_rent`` and its dated
amounts in ``RentPeriod``; the ledger charges the dated amount. Reading ``monthly_rent``
on a screen therefore shows staff (and the tenant) a figure the tenancy no longer pays.
(ADR-028 conformance; audit F15's "current monthly rent".)
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from tests.factories import make_lease, make_manager, make_nnn_rate, make_rent_period, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def _stepped_lease(*, carries_nnn=False):
    lease = make_lease(
        start_date=(TODAY.replace(day=1) - dt.timedelta(days=90)).replace(day=1),
        monthly_rent=Decimal("1500.00"),
        template="STEP_UP",
        step_up_month=1,
        step_up_percent=Decimal("10.00"),
        carries_nnn=carries_nnn,
    )
    make_rent_period(lease, effective_from=lease.start_date, amount=Decimal("1500.00"))
    make_rent_period(lease, effective_from=TODAY.replace(day=1), amount=Decimal("1650.00"))
    if carries_nnn:
        make_nnn_rate(lease, effective_from=lease.start_date, monthly_amount=Decimal("305.00"))
    return lease


def _body(response):
    return " ".join(strip_tags(response.content.decode()).split())


def test_the_unit_page_shows_the_rent_the_tenancy_pays_now(client):
    lease = _stepped_lease()
    client.force_login(make_manager())

    body = _body(client.get(reverse("portfolio:unit-detail", args=[lease.unit_id])))

    assert "$1,650.00" in body, "the dated amount now in force"
    assert "$1,500.00" not in body, "not the starting rent"
    assert "Current monthly rent" in body


def test_the_property_page_shows_the_current_rent(client):
    lease = _stepped_lease()
    client.force_login(make_manager())

    body = _body(client.get(reverse("portfolio:property-detail", args=[lease.unit.property_id])))

    assert "$1,650.00 / month" in body
    assert "$1,500.00" not in body


def test_the_lease_list_shows_the_current_rent(client):
    _stepped_lease()
    client.force_login(make_manager())

    body = _body(client.get(reverse("leases:lease-list")))

    assert "$1,650.00" in body
    assert "$1,500.00" not in body


def test_the_tenant_payment_header_shows_the_current_rent(client):
    tenant = make_tenant(username="current-rent")
    lease = _stepped_lease()
    lease.lease_tenants.create(tenant=tenant, is_primary=True)
    client.force_login(tenant)

    body = _body(client.get(reverse("payments:home")))

    assert "$1,650.00" in body
    assert "$1,500.00" not in body


def test_the_unit_page_separates_current_nnn(client):
    lease = _stepped_lease(carries_nnn=True)
    client.force_login(make_manager())

    body = _body(client.get(reverse("portfolio:unit-detail", args=[lease.unit_id])))

    assert "$1,650.00" in body
    assert "NNN" in body and "$305.00" in body


def test_a_fixed_lease_still_shows_its_one_rent(client):
    lease = make_lease(monthly_rent=Decimal("1850.00"))
    client.force_login(make_manager())

    body = _body(client.get(reverse("portfolio:unit-detail", args=[lease.unit_id])))

    assert "$1,850.00" in body
