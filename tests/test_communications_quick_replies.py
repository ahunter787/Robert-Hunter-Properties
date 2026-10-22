"""E15.1: staff-only quick replies; tenants never receive template data."""

import pytest
from django.urls import reverse

from apps.communications.models import QuickReply
from tests.factories import make_lease, make_manager, make_tenant
from tests.test_communications import start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def world():
    manager = make_manager(username="qr-manager")
    tenant = make_tenant(username="qr-tenant")
    lease = make_lease(tenants=[tenant])
    message = start(manager, lease, tenant=tenant, body="Hello")
    return manager, tenant, lease, message.conversation


def test_a_manager_creates_uses_and_disables_a_quick_reply(client, world):
    manager, _, _, conversation = world
    client.force_login(manager)
    response = client.post(
        reverse("communications:quick-reply-new"),
        {"label": "Rent reminder", "body": "Your rent is due soon.", "property": ""},
    )
    assert response.status_code == 302
    reply = QuickReply.objects.get()
    assert reply.created_by == manager

    thread = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert b"Rent reminder" in thread.content
    assert b"Your rent is due soon." in thread.content

    response = client.post(reverse("communications:quick-reply-toggle", args=[reply.pk]))
    assert response.status_code == 302
    reply.refresh_from_db()
    assert reply.is_active is False


def test_a_tenant_cannot_reach_quick_replies_or_receive_them(client, world):
    _, tenant, _, conversation = world
    QuickReply.objects.create(label="Staff only", body="Internal template", created_by=None)
    client.force_login(tenant)
    assert client.get(reverse("communications:quick-replies")).status_code == 403
    assert (
        client.get(
            reverse("tenant_communications:conversation", args=[conversation.public_id])
        ).status_code
        == 200
    )
    response = client.get(
        reverse("tenant_communications:conversation", args=[conversation.public_id])
    )
    assert b"Staff only" not in response.content
    assert b"Internal template" not in response.content
    assert b"quick-reply" not in response.content


def test_quick_replies_can_be_scoped_to_a_property(client, world):
    manager, _, lease, conversation = world
    other = make_lease()
    QuickReply.objects.create(label="This property", body="Scoped", property=lease.unit.property)
    QuickReply.objects.create(label="Other property", body="Other", property=other.unit.property)
    client.force_login(manager)
    response = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert b"This property" in response.content
    assert b"Other property" not in response.content
