"""E15.2–E15.5: inbox preferences, exports, shared media and internal notes."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.communications import delivery
from apps.communications.models import ConversationPreference, InternalNote
from tests.factories import make_lease, make_manager, make_tenant
from tests.test_communications import reply, start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@pytest.fixture
def world():
    manager = make_manager(username="e15-manager")
    other_manager = make_manager(username="e15-other-manager")
    tenant = make_tenant(username="e15-tenant")
    lease = make_lease(tenants=[tenant])
    message = start(manager, lease, tenant=tenant, body="Hello")
    return manager, other_manager, tenant, message.conversation


def test_archive_is_per_manager_and_does_not_hide_the_thread_from_others(client, world):
    manager, other_manager, _, conversation = world
    client.force_login(manager)
    response = client.post(
        reverse("communications:conversation-archive", args=[conversation.public_id]),
        {"archived": "1"},
    )
    assert response.status_code == 302
    assert ConversationPreference.objects.get(user=manager).archived_at is not None

    assert conversation.public_id not in [
        row.public_id
        for row in client.get(reverse("communications:index")).context["page"].object_list
    ]
    archived = client.get(reverse("communications:index") + "?archived=1")
    assert conversation.public_id in [row.public_id for row in archived.context["page"].object_list]

    client.force_login(other_manager)
    assert conversation.public_id in [
        row.public_id
        for row in client.get(reverse("communications:index")).context["page"].object_list
    ]


def test_mute_suppresses_only_that_manager_email(client, world):
    manager, other_manager, tenant, conversation = world
    from apps.communications import services

    services.set_preference(conversation, actor=manager, mute=True)
    with patch.object(delivery, "_queue") as queue:
        reply(conversation, tenant, body="A new tenant reply")
    recipients = [call.kwargs["recipient"] for call in queue.call_args_list]
    assert manager not in recipients
    assert other_manager in recipients


def test_internal_notes_are_staff_only_and_not_in_exports(client, world):
    manager, _, tenant, conversation = world
    client.force_login(manager)
    response = client.post(
        reverse("communications:conversation-note", args=[conversation.public_id]),
        {"body": "Only the office should see this."},
    )
    assert response.status_code == 302
    assert InternalNote.objects.get().body == "Only the office should see this."

    export = client.get(
        reverse("communications:conversation-export", args=[conversation.public_id, "txt"])
    )
    assert b"Only the office should see this" not in export.content

    client.force_login(tenant)
    assert (
        client.post(
            reverse("communications:conversation-note", args=[conversation.public_id]),
            {"body": "Tenant attempt"},
        ).status_code
        == 403
    )
    thread = client.get(
        reverse("tenant_communications:conversation", args=[conversation.public_id])
    )
    assert b"Only the office should see this" not in thread.content


def test_shared_media_and_export_include_attachment_names(client, world):
    manager, _, _, conversation = world
    upload = SimpleUploadedFile("lease.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    reply(conversation, manager, body="Attached", files=[upload], token=uuid4())
    client.force_login(manager)
    thread = client.get(reverse("communications:conversation", args=[conversation.public_id]))
    assert b"lease.pdf" in thread.content
    export = client.get(
        reverse("communications:conversation-export", args=[conversation.public_id, "csv"])
    )
    assert export.status_code == 200
    assert b"lease.pdf" in export.content
