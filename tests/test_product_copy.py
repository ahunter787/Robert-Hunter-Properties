"""Rendered product pages contain product language, not development commentary."""

import re

import pytest
from django.urls import reverse

from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db

FORBIDDEN_PRODUCT_COPY = (
    re.compile(r"\bphase\s+\d+\b", re.IGNORECASE),
    re.compile(r"docs/roadmap", re.IGNORECASE),
    re.compile(r"being built", re.IGNORECASE),
    re.compile(r"not modelled", re.IGNORECASE),
    re.compile(r"not modeled", re.IGNORECASE),
    re.compile(r"\bships\b", re.IGNORECASE),
)


def assert_product_copy(*responses):
    # A refusal, a 404 or a redirect renders an error page, which would pass a copy check
    # trivially while the page a person asked for was never rendered at all.
    for response in responses:
        assert response.status_code == 200, (
            f"{response.request.get('PATH_INFO', '?')} answered {response.status_code}, so its "
            "copy was never checked"
        )
    rendered = "\n".join(response.content.decode() for response in responses)
    for pattern in FORBIDDEN_PRODUCT_COPY:
        assert pattern.search(rendered) is None, (
            f"Rendered product copy contains {pattern.pattern!r}"
        )


def test_public_and_authentication_pages_have_no_development_copy(client):
    assert_product_copy(client.get(reverse("home")), client.get(reverse("accounts:login")))


def test_representative_staff_pages_have_no_development_copy(client):
    lease = make_lease()
    client.force_login(make_manager(username="copy-manager"))

    assert_product_copy(
        client.get(reverse("manage:home")),
        client.get(reverse("portfolio:property-detail", args=[lease.unit.property_id])),
        client.get(reverse("leases:lease-detail", args=[lease.pk])),
        client.get(reverse("ledger:overview")),
        client.get(reverse("ledger:lease-ledger", args=[lease.pk])),
    )


def test_representative_tenant_pages_have_no_development_copy(client):
    tenant = make_tenant(username="copy-tenant")
    make_lease(tenants=[tenant])
    client.force_login(tenant)

    assert_product_copy(
        client.get(reverse("accounts:home")),
        client.get(reverse("tenancy:lease")),
        client.get(reverse("payments:home")),
    )
