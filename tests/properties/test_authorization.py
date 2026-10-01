"""The portfolio role matrix, route by route.

Specification Phase 2 grants managers the portfolio; maintenance staff and tenants
must not reach it at all, and destruction stays with admins.
"""

import pytest
from django.urls import reverse

from tests.factories import (
    make_admin,
    make_maintenance,
    make_manager,
    make_property,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db


def portfolio_urls(property_, unit):
    """Every portfolio route with the kwargs it needs."""
    return {
        "property-list": (reverse("portfolio:property-list"), {}),
        "property-create": (reverse("portfolio:property-create"), {}),
        "property-detail": (reverse("portfolio:property-detail", args=[property_.pk]), {}),
        "property-update": (reverse("portfolio:property-update", args=[property_.pk]), {}),
        "property-delete": (reverse("portfolio:property-delete", args=[property_.pk]), {}),
        "property-toggle": (
            reverse("portfolio:property-toggle-active", args=[property_.pk]),
            {},
        ),
        "unit-list": (reverse("portfolio:unit-list"), {}),
        "unit-create": (reverse("portfolio:unit-create"), {}),
        "unit-detail": (reverse("portfolio:unit-detail", args=[unit.pk]), {}),
        "unit-update": (reverse("portfolio:unit-update", args=[unit.pk]), {}),
        "unit-delete": (reverse("portfolio:unit-delete", args=[unit.pk]), {}),
        "unit-toggle": (reverse("portfolio:unit-toggle-active", args=[unit.pk]), {}),
    }


@pytest.fixture
def records():
    property_ = make_property()
    unit = make_unit(property_, identifier="A")
    return property_, unit


@pytest.mark.parametrize("maker", [make_tenant, make_maintenance], ids=["tenant", "maintenance"])
def test_roles_outside_the_portfolio_are_forbidden(client, records, maker):
    property_, unit = records
    client.force_login(maker(username=f"outsider-{maker.__name__}"))

    for name, (url, _) in portfolio_urls(property_, unit).items():
        response = client.get(url)
        assert response.status_code == 403, f"{name} should be forbidden"
        assert b"403" in response.content, f"{name} should render the 403 page"


@pytest.mark.parametrize("maker", [make_tenant, make_maintenance], ids=["tenant", "maintenance"])
def test_roles_outside_the_portfolio_cannot_change_state(client, records, maker):
    property_, unit = records
    client.force_login(maker(username=f"outsider-post-{maker.__name__}"))

    assert (
        client.post(reverse("portfolio:property-toggle-active", args=[property_.pk])).status_code
        == 403
    )
    assert client.post(reverse("portfolio:unit-toggle-active", args=[unit.pk])).status_code == 403
    assert client.post(reverse("portfolio:property-create"), {}).status_code == 403
    assert client.post(reverse("portfolio:unit-create"), {}).status_code == 403


def test_anonymous_visitors_are_sent_to_sign_in(client, records):
    property_, unit = records

    for name, (url, _) in portfolio_urls(property_, unit).items():
        response = client.get(url)
        assert response.status_code == 302, f"{name} should redirect"
        assert reverse("accounts:login") in response["Location"]


def test_a_manager_runs_the_portfolio_but_cannot_delete(client, records):
    property_, unit = records
    client.force_login(make_manager(username="portfolio-manager"))

    assert client.get(reverse("portfolio:property-list")).status_code == 200
    assert client.get(reverse("portfolio:property-create")).status_code == 200
    assert client.get(reverse("portfolio:property-detail", args=[property_.pk])).status_code == 200
    assert client.get(reverse("portfolio:property-update", args=[property_.pk])).status_code == 200
    assert client.get(reverse("portfolio:unit-list")).status_code == 200
    assert client.get(reverse("portfolio:unit-detail", args=[unit.pk])).status_code == 200

    assert client.get(reverse("portfolio:property-delete", args=[property_.pk])).status_code == 403
    assert client.get(reverse("portfolio:unit-delete", args=[unit.pk])).status_code == 403


def test_an_admin_may_reach_every_portfolio_page(client, records):
    property_, unit = records
    client.force_login(make_admin(username="portfolio-admin"))

    routes = portfolio_urls(property_, unit)
    for name, (url, _) in routes.items():
        if name.endswith("toggle"):
            continue  # state changes are POST-only
        response = client.get(url)
        assert response.status_code == 200, f"{name} should be reachable by an admin"

    for name in ("property-toggle", "unit-toggle"):
        assert client.get(routes[name][0]).status_code == 405


def test_a_manager_can_read_tenants_but_not_administer_them(client, records):
    tenant = make_tenant(username="visible-tenant")
    client.force_login(make_manager(username="tenant-reading-manager"))

    assert client.get(reverse("manage:account-list")).status_code == 200
    assert client.get(reverse("manage:account-detail", args=[tenant.pk])).status_code == 200

    assert client.get(reverse("manage:account-create")).status_code == 403
    assert client.post(reverse("manage:account-toggle-active", args=[tenant.pk])).status_code == 403
    assert (
        client.post(
            reverse("manage:account-role", args=[tenant.pk]), {"role": "MANAGER"}
        ).status_code
        == 403
    )


def test_tenant_list_hides_the_invite_button_from_managers(client):
    client.force_login(make_manager(username="no-invite-manager"))

    body = client.get(reverse("manage:account-list")).content.decode()

    assert "New tenant" not in body
