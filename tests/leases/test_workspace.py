"""Lease sections preserve real financial projections and permission gates."""

import pytest
from django.urls import reverse

from tests.factories import make_lease, make_maintenance, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


def test_lease_opens_financial_workspace_and_links_local_sections(client):
    client.force_login(make_manager())
    lease = make_lease(make_unit(), tenants=[make_tenant()])
    response = client.get(reverse("leases:lease-detail", args=[lease.pk]))
    assert response.context["lease_section"] == "ledger"
    assert b"Transactions" in response.content
    assert b'aria-label="Lease sections"' in response.content
    assert b"section=documents" in response.content
    assert b"Back to" not in response.content
    for section in ("terms", "rent", "tenants", "documents"):
        result = client.get(reverse("leases:lease-detail", args=[lease.pk]), {"section": section})
        assert result.status_code == 200
        assert result.context["lease_section"] == section
        assert b"Chronological transactions" not in result.content


def test_invalid_section_and_external_context_do_not_change_scope(client):
    client.force_login(make_manager())
    lease = make_lease(make_unit(), tenants=[make_tenant()])
    response = client.get(
        reverse("leases:lease-detail", args=[lease.pk]),
        {
            "section": "https://example.org/",
            "return": "https://example.org/",
            "q": "Studio",
            "status": "ACTIVE",
        },
    )
    assert response.context["lease_section"] == "ledger"
    assert b"example.org" not in response.content
    assert all("q=Studio" in tab["url"] for tab in response.context["lease_tabs"])


@pytest.mark.parametrize("factory", [make_tenant, make_maintenance])
def test_non_managers_cannot_read_staff_lease_sections(client, factory):
    user = factory()
    client.force_login(user)
    lease = make_lease(make_unit())
    for section in ("ledger", "terms", "tenants", "documents"):
        response = client.get(reverse("leases:lease-detail", args=[lease.pk]), {"section": section})
        assert response.status_code == 403
