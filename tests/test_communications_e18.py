"""E18: the shell and messenger projection keep the server authoritative."""

from uuid import uuid4

import pytest
from django.urls import reverse

from tests.factories import make_lease, make_manager, make_tenant
from tests.test_communications import start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mail(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


def world():
    manager = make_manager(username="e18-manager")
    tenant = make_tenant(username="e18-tenant", first_name="Alex", last_name="Example")
    lease = make_lease(tenants=[tenant])
    message = start(tenant, lease, tenant=tenant, body="Where may guests park?")
    return manager, tenant, message.conversation


def test_inbox_has_dense_rows_latest_snippet_and_unread_count(client):
    manager, _, conversation = world()
    client.force_login(manager)
    response = client.get(reverse("communications:index"))
    assert response.status_code == 200
    row = response.context["page"].object_list[0]
    assert row.public_id == conversation.public_id
    assert row.latest_body == "Where may guests park?"
    assert row.unread_count == 1
    assert response.context["portal_unread"] == 1
    assert b"chat-row" in response.content
    assert b"Where may guests park?" in response.content
    assert b"chat-page" in response.content


def test_conversation_renders_chat_shell_and_composer(client):
    manager, _, conversation = world()
    client.force_login(manager)
    response = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert response.status_code == 200
    assert b"chat-page" in response.content
    assert b"data-chat-composer" in response.content
    assert b"data-conversation-stream" in response.content
    assert b"data-message-batch" in response.content
    assert b'data-initial-bottom="1"' in response.content
    # The composer is a real form, not JS-only.
    assert b'<form method="post" enctype="multipart/form-data"' in response.content


def test_ajax_send_returns_a_batch_without_redirect(client):
    manager, _, conversation = world()
    client.force_login(manager)
    url = reverse("communications:conversation", args=[conversation.public_id])
    token = uuid4()
    response = client.post(
        url,
        {"body": "Thanks — driveway only.", "token": token},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    assert b"data-message-batch" in response.content
    assert b"Thanks" in response.content
    assert not response.get("Location")
    assert conversation.messages.filter(body="Thanks — driveway only.").count() == 1


def test_ajax_empty_message_returns_composer_error(client):
    manager, _, conversation = world()
    client.force_login(manager)
    response = client.post(
        reverse("communications:conversation", args=[conversation.public_id]),
        {"body": "", "token": uuid4()},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 422
    assert b"composer-error" in response.content
    assert b"Enter a message or attach a file." in response.content


def test_messaging_rail_uses_the_same_visible_scope(client):
    manager, tenant, conversation = world()
    other_tenant = make_tenant(username="e18-other", first_name="Blair", last_name="Example")
    other_lease = make_lease(tenants=[other_tenant])
    start(other_tenant, other_lease, tenant=other_tenant, body="Unrelated thread")
    client.force_login(manager)
    response = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert b"Where may guests park?" in response.content
    # A manager sees the portfolio inbox; a tenant must not see another tenancy.
    assert b"Unrelated thread" in response.content
    client.force_login(tenant)
    response = client.get(
        reverse("tenant_communications:conversation", args=[conversation.public_id])
    )
    assert response.status_code == 200
    assert b"Internal notes" not in response.content
    assert b"Unrelated thread" not in response.content


def test_thread_keeps_a_no_javascript_fallback(client):
    manager, _, conversation = world()
    client.force_login(manager)
    response = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert response.status_code == 200
    body = response.content
    assert b'class="manual-read"' in body
    assert b"Mark displayed messages read" in body
    assert b"<noscript>" not in body
    # The composer is a normal POST form; JavaScript only enhances it.
    assert b'action="' in body and b'method="post"' in body
