"""The staff landing page shows each role only numbers it can act on."""

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


def board(client, user):
    """Sign in and fetch the staff landing page (the response, so context is available)."""
    client.force_login(user)
    return client.get(reverse("manage:home"))


def test_a_manager_sees_portfolio_counts(client):
    make_unit(make_property(name="One"), identifier="A")
    make_unit(make_property(name="Two"), identifier="A", is_active=False)

    response = board(client, make_manager(username="counting-manager"))

    assert response.context["property_active_count"] == 2
    assert response.context["property_total_count"] == 2
    assert response.context["unit_active_count"] == 1
    assert response.context["unit_total_count"] == 2
    assert "in service of 2 total" in response.content.decode()


def test_a_manager_sees_the_active_tenant_count(client):
    make_tenant(username="active-tenant")
    inactive = make_tenant(username="inactive-tenant")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    response = board(client, make_manager(username="tenant-counting-manager"))

    assert response.context["tenant_active_count"] == 1
    assert "active accounts" in response.content.decode()


def test_a_manager_does_not_see_invitation_administration(client):
    make_tenant(username="plain-tenant")

    response = board(client, make_manager(username="plain-manager"))
    body = response.content.decode()

    assert "tenant_invited_count" not in response.context
    assert "Invitations" not in body
    assert "Invite a tenant" not in body


def test_an_admin_sees_the_invitation_count(client):
    response = board(client, make_admin(username="counting-admin"))
    body = response.content.decode()

    assert "tenant_invited_count" in response.context
    assert "Invitations" in body
    assert "Invite a tenant" in body


def test_a_maintenance_user_sees_neither_board(client):
    make_property()

    response = board(client, make_maintenance(username="maintenance-board"))
    body = response.content.decode()

    assert "property_active_count" not in response.context
    assert "in service of" not in body
    assert "Invitations" not in body
    assert "Your access" in body


def test_the_board_says_what_is_not_counted_yet(client):
    body = board(client, make_manager(username="honest-manager")).content.decode()

    assert "Not counted yet" in body
    assert "Phase 3" in body
