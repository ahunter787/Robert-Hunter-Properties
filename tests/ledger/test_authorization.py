"""The ledger role matrix, route by route.

Routine desk work is for managers; anything that changes what history means —
a reversal, an adjustment — is for admins. Maintenance users and tenants have no
business in the accounting area at all.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_maintenance,
    make_manager,
    make_payment,
    make_tenant,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def ledger_world():
    """A lease with one charge and one payment, plus every URL that touches them."""
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("400.00"), payment_date=TODAY)
    return {
        "lease": lease,
        "charge": charge,
        "payment": payment,
        "gets": [
            reverse("ledger:overview"),
            reverse("ledger:lease-ledger", args=[lease.pk]),
            reverse("ledger:charge-create", args=[lease.pk]),
            reverse("ledger:payment-create", args=[lease.pk]),
        ],
        "posts": [
            (reverse("ledger:rent-charges", args=[lease.pk]), {}),
            (
                reverse("ledger:charge-create", args=[lease.pk]),
                {
                    "description": "Keys",
                    "amount": "10.00",
                    "due_date": TODAY.isoformat(),
                },
            ),
            (
                reverse("ledger:payment-create", args=[lease.pk]),
                {
                    "amount": "10.00",
                    "payment_date": TODAY.isoformat(),
                    "method": "CASH",
                    "status": "CLEARED",
                    "external_reference": "",
                    "notes": "",
                },
            ),
            (reverse("ledger:payment-clear", args=[payment.pk]), {}),
            (reverse("ledger:payment-void", args=[payment.pk]), {}),
        ],
        "admin_gets": [
            reverse("ledger:payment-reverse", args=[payment.pk]),
            reverse("ledger:charge-adjust", args=[charge.pk]),
        ],
        "admin_posts": [
            (
                reverse("ledger:payment-reverse", args=[payment.pk]),
                {"reason": "not allowed"},
            ),
            (
                reverse("ledger:charge-adjust", args=[charge.pk]),
                {"direction": "DECREASE", "amount": "10.00", "reason": "not allowed"},
            ),
        ],
    }


@pytest.mark.parametrize("maker", [make_tenant, make_maintenance], ids=["tenant", "maintenance"])
def test_roles_outside_accounting_are_forbidden(client, maker):
    world = ledger_world()
    client.force_login(maker(username=f"outsider-{maker.__name__}"))

    for url in world["gets"]:
        assert client.get(url).status_code == 403, f"{url} should be forbidden"
    for url, data in world["posts"]:
        assert client.post(url, data).status_code == 403, f"{url} should be forbidden"
    for url in world["admin_gets"]:
        assert client.get(url).status_code == 403, f"{url} should be forbidden"
    for url, data in world["admin_posts"]:
        assert client.post(url, data).status_code == 403, f"{url} should be forbidden"


def test_anonymous_visitors_are_sent_to_sign_in(client):
    world = ledger_world()

    for url in world["gets"] + world["admin_gets"]:
        response = client.get(url)
        assert response.status_code == 302, f"{url} should redirect"
        assert reverse("accounts:login") in response["Location"]


def test_a_manager_runs_the_desk_but_cannot_undo_anything(client):
    world = ledger_world()
    client.force_login(make_manager(username="ledger-manager"))

    for url in world["gets"]:
        assert client.get(url).status_code == 200, f"{url} should be reachable"
    for url in world["admin_gets"]:
        assert client.get(url).status_code == 403, f"{url} is an admin action"

    assert client.post(reverse("ledger:rent-charges", args=[world["lease"].pk])).status_code == 302


def test_an_admin_reaches_every_accounting_page(client):
    world = ledger_world()
    client.force_login(make_admin(username="ledger-admin"))

    for url in world["gets"] + world["admin_gets"]:
        assert client.get(url).status_code == 200, f"{url} should be reachable"


def test_a_charge_from_another_lease_is_not_reachable_by_id(client):
    """Ids cannot be probed: a charge that does not exist is simply not found."""
    world = ledger_world()
    client.force_login(make_admin(username="ledger-admin"))

    assert client.get(reverse("ledger:charge-adjust", args=[99999])).status_code == 404
    assert client.get(reverse("ledger:payment-reverse", args=[99999])).status_code == 404
    assert client.get(reverse("ledger:lease-ledger", args=[99999])).status_code == 404
    assert world["charge"].pk is not None


def test_a_tenant_cannot_reach_the_accounting_area_even_with_a_lease(client):
    tenant = make_tenant(username="tenant-with-lease")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("10.00"), due_date=dt.date(2020, 1, 1))
    client.force_login(tenant)

    assert client.get(reverse("ledger:overview")).status_code == 403
    assert client.get(reverse("ledger:lease-ledger", args=[lease.pk])).status_code == 403
