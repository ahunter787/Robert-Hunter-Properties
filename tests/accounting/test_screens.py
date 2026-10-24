"""B1 staff screens: manager-only, tied to the same ledger, no tenant exposure."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.ledger.models import ChargeKind
from apps.ledger.services import create_charge
from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db


def signed_in(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


def test_a_manager_can_read_the_accounting_overview_and_control():
    lease = make_lease()
    create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=lease.start_date,
        kind=ChargeKind.RENT,
    )
    client = signed_in(make_manager(username="accounting-overview"))

    overview = client.get(reverse("accounting:overview"))
    assert overview.status_code == 200
    assert overview.context["tie"]["difference"] == Decimal("0.00")
    assert overview.context["journal_count"] == 1
    assert b"Accounting tasks" in overview.content
    assert b"Trial balance" in overview.content
    assert b"Record a bill" in overview.content
    assert client.get(reverse("accounting:control")).status_code == 200
    assert client.get(reverse("accounting:chart")).status_code == 200
    assert client.get(reverse("accounting:journal-list")).status_code == 200


def test_a_manager_can_open_a_journal_detail():
    lease = make_lease()
    charge = create_charge(
        lease,
        description="Rent",
        amount=Decimal("100.00"),
        due_date=lease.start_date,
        kind=ChargeKind.RENT,
    )
    client = signed_in(make_manager(username="accounting-journal"))
    from apps.accounting.models import JournalEntry

    entry = JournalEntry.objects.get(source_key=f"charge:{charge.pk}:created")
    response = client.get(reverse("accounting:journal-detail", args=[entry.pk]))

    assert response.status_code == 200
    assert response.context["entry"] == entry
    assert b"4000" in response.content


def test_tenants_cannot_reach_accounting_screens():
    tenant = make_tenant(username="accounting-outsider")
    client = signed_in(tenant)
    for name in ("overview", "chart", "journal-list", "control"):
        assert client.get(reverse(f"accounting:{name}")).status_code == 403
