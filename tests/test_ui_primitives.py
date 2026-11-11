"""Rendered checks for the shared live-screen layout primitives."""

import pytest
from django.urls import reverse

from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db


def test_tenancy_actions_share_one_bar_and_button_variant(client):
    manager = make_manager(username="ui-primitives-manager")
    tenant = make_tenant(username="ui-primitives-tenant")
    make_lease(tenants=[tenant])
    client.force_login(manager)

    body = client.get(
        reverse("manage:account-detail", args=[tenant.pk]), {"section": "overview"}
    ).content.decode()

    assert 'class="rhp-action-bar"' in body
    assert "Lease workspace" in body
    assert "Lease ledger" in body
    assert body.count('class="rhp-btn rhp-btn-secondary"') >= 2
    assert 'class="rhp-link" href="' in body  # links elsewhere on the card remain links


def test_ledger_actions_use_the_shared_action_bar(client):
    manager = make_manager(username="ui-ledger-manager")
    lease = make_lease(tenants=[make_tenant(username="ui-ledger-tenant")])
    client.force_login(manager)

    body = client.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()

    assert 'class="rhp-action-bar mt-4"' in body
    assert "Record payment" in body
