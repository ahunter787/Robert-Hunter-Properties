"""Phase 8: privacy, snapshots, immutable history, retries and real forms."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.communications import delivery, services
from apps.communications.models import (
    Announcement,
    AnnouncementRecipient,
    AnnouncementVersion,
    Attachment,
    Conversation,
    Message,
    Notification,
    ReadPosition,
)
from apps.leases.models import LeaseTenant
from tests.factories import make_lease, make_maintenance, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@pytest.fixture
def household():
    manager = make_manager(email="manager@example.test")
    a = make_tenant(username="alex", email="alex@example.test")
    b = make_tenant(username="blair", email="blair@example.test")
    lease = make_lease(tenants=[a, b])
    return manager, a, b, lease


def start(
    actor,
    lease,
    *,
    tenant=None,
    visibility="PRIVATE",
    body="Please contact RHP.",
    files=None,
    **kwargs,
):
    token, _ = services.review_conversation(
        actor=actor,
        lease=lease,
        subject="Test conversation",
        visibility=visibility,
        tenant=tenant,
        **kwargs,
    )
    return services.start_conversation(
        actor=actor,
        review=token,
        body=body,
        files=files or [],
        token=uuid4(),
        portal_base="http://testserver",
    )


def reply(conversation, actor, **kwargs):
    return services.send_message(
        conversation,
        actor=actor,
        body=kwargs.pop("body", "Reply"),
        files=kwargs.pop("files", []),
        token=kwargs.pop("token", uuid4()),
        portal_base="http://testserver",
        **kwargs,
    )


def draft(manager, *, important=False, properties=()):
    return services.save_draft(
        actor=manager,
        title="Water service",
        body="Service interruption.",
        important=important,
        expires_at=None,
        properties=properties,
    )


def publish(row, manager, **kwargs):
    version = row.latest or row
    review, _ = services.review_announcement(
        row,
        actor=manager,
        title=kwargs.get("title", version.title),
        body=kwargs.get("body", version.body),
        important=kwargs.get("important", version.important),
        expires_at=kwargs.get("expires_at", version.expires_at),
        reason=kwargs.get("reason", ""),
    )
    return services.publish_announcement(
        actor=manager, review=review, portal_base="http://testserver"
    )


def test_private_shared_and_forged_object_boundaries(client, household):
    manager, a, b, lease = household
    private = start(a, lease).conversation
    shared = start(manager, lease, visibility="SHARED").conversation
    assert not Conversation.objects.visible_to(b).filter(pk=private.pk).exists()
    assert Conversation.objects.visible_to(b).filter(pk=shared.pk).exists()
    client.force_login(b)
    assert (
        client.get(
            reverse("tenant_communications:conversation", args=[private.public_id])
        ).status_code
        == 404
    )
    assert (
        client.get(
            reverse("tenant_communications:conversation", args=[shared.public_id])
        ).status_code
        == 200
    )
    assert client.get(reverse("communications:index")).status_code == 403
    client.force_login(make_maintenance())
    assert client.get(reverse("communications:index")).status_code == 403
    assert (
        client.post(
            reverse("communications:work", args=[shared.public_id]), {"action": "handled"}
        ).status_code
        == 403
    )


def test_membership_change_freezes_history_even_after_membership_restored(household):
    manager, a, b, lease = household
    thread = start(a, lease, visibility="SHARED").conversation
    membership = LeaseTenant.objects.get(lease=lease, tenant=b)
    membership.delete()
    thread.refresh_from_db()
    assert thread.frozen_at
    LeaseTenant.objects.create(lease=lease, tenant=b)
    assert not services.can_send(thread, a)
    assert Conversation.objects.visible_to(b).filter(pk=thread.pk).exists()
    with pytest.raises(ValidationError):
        reply(thread, manager)
    with pytest.raises(ValidationError):
        services.change_work(thread, actor=manager, action="enable-followup", reason="Restore")
    newcomer = make_tenant(username="newcomer")
    LeaseTenant.objects.create(lease=lease, tenant=newcomer)
    assert not Conversation.objects.visible_to(newcomer).filter(pk=thread.pk).exists()


def test_moveout_followup_does_not_change_occupancy_or_account(household):
    manager, a, _, lease = household
    thread = start(a, lease).conversation
    lease.status, lease.ended_on, lease.end_reason = "ENDED", timezone.localdate(), "MUTUAL"
    lease.save()
    assert not services.can_send(thread, a)
    with pytest.raises(ValidationError):
        services.change_work(thread, actor=manager, action="enable-followup")
    services.change_work(
        thread, actor=manager, action="enable-followup", reason="Discuss forwarding address"
    )
    thread.refresh_from_db()
    reply(thread, a)
    lease.refresh_from_db()
    assert lease.status == "ENDED"
    assert lease.account_status == "OPEN"
    services.change_work(thread, actor=manager, action="disable-followup", reason="Complete")
    thread.refresh_from_db()
    assert not services.can_send(thread, a)


def test_messages_after_moveout_use_plain_language(client, household):
    manager, a, _, lease = household
    thread = start(a, lease).conversation
    lease.status, lease.ended_on, lease.end_reason = "ENDED", timezone.localdate(), "MUTUAL"
    lease.save()
    client.force_login(manager)
    form = client.get(reverse("communications:new"), {"lease": lease.pk})
    assert b"Allow messages after move-out" in form.content
    assert b"does not reactivate the lease or financial account" in form.content
    assert b"scoped follow-up" not in form.content.lower()
    detail = reverse("communications:conversation", args=[thread.public_id])
    response = client.get(detail)
    assert b"Allow messages after move-out" in response.content
    assert b"scoped follow-up" not in response.content.lower()
    services.change_work(thread, actor=manager, action="enable-followup", reason="Return keys")
    response = client.get(detail)
    assert b"Messages after move-out are allowed in this conversation" in response.content
    assert b"Turn off messages after move-out" in response.content
    client.force_login(a)
    response = client.get(reverse("tenant_communications:conversation", args=[thread.public_id]))
    assert b"Messages after move-out are allowed in this conversation" in response.content
    assert b"scoped follow-up" not in response.content.lower()


def test_create_review_is_read_only_and_rejects_household_change(household):
    _, a, _, lease = household
    review, _ = services.review_conversation(
        actor=a, lease=lease, subject="Hello", visibility="SHARED"
    )
    assert not Conversation.objects.exists()
    LeaseTenant.objects.create(lease=lease, tenant=make_tenant(username="added"))
    with pytest.raises(ValidationError):
        services.start_conversation(
            actor=a,
            review=review,
            body="Hello",
            files=[],
            token=uuid4(),
            portal_base="http://testserver",
        )
    assert not Message.objects.exists()


def test_idempotency_and_work_state_are_independent_of_reads(household):
    manager, a, b, lease = household
    message = start(a, lease, visibility="SHARED")
    thread = message.conversation
    services.mark_read(thread, actor=manager, message_id=message.pk)
    thread.refresh_from_db()
    assert thread.state == "NEEDS_RHP"
    token = uuid4()
    one = reply(thread, manager, token=token)
    two = reply(thread, manager, token=token)
    assert one.pk == two.pk
    thread.refresh_from_db()
    assert thread.state == "WAITING"
    with pytest.raises(ValidationError):
        reply(thread, manager, token=token, body="Different content")
    services.change_work(thread, actor=manager, action="handled")
    reply(thread, b)
    thread.refresh_from_db()
    assert thread.state == "NEEDS_RHP"
    services.mark_read(thread, actor=a, message_id=one.pk)
    services.mark_read(thread, actor=a, message_id=message.pk)
    assert ReadPosition.objects.get(conversation=thread, user=a).message_id == one.pk
    assert not ReadPosition.objects.filter(conversation=thread, user=b).exists()


def test_message_and_recipient_history_immutable(household):
    _, a, _, lease = household
    message = start(a, lease)
    message.body = "Overwrite"
    with pytest.raises(ValidationError):
        message.save()
    with pytest.raises(ValidationError):
        Message.objects.filter(pk=message.pk).update(body="Overwrite")
    with pytest.raises(ValidationError):
        message.delete()
    with pytest.raises(ValidationError):
        message.conversation.participants.all().delete()


def test_attachments_private_and_limits(client, household):
    _, a, b, lease = household
    upload = SimpleUploadedFile(
        "readable notice.pdf", b"%PDF-1.4 synthetic", content_type="application/pdf"
    )
    message = start(a, lease, files=[upload], body="")
    attachment = message.attachments.get()
    assert "readable" not in attachment.file.name
    client.force_login(a)
    response = client.get(reverse("tenant_communications:attachment", args=[attachment.public_id]))
    assert response.status_code == 200
    assert b"%PDF" in b"".join(response.streaming_content)
    client.force_login(b)
    assert (
        client.get(
            reverse("tenant_communications:attachment", args=[attachment.public_id])
        ).status_code
        == 404
    )
    with pytest.raises(ValidationError):
        reply(message.conversation, a, files=[SimpleUploadedFile("x.exe", b"bad")])
    with pytest.raises(ValidationError):
        reply(
            message.conversation,
            a,
            files=[SimpleUploadedFile(f"{i}.pdf", b"%PDF") for i in range(11)],
        )


def test_rate_limit_counts_failed_attempts(settings, household):
    _, a, _, lease = household
    thread = start(a, lease).conversation
    settings.RHP_COMMUNICATION_SEND_LIMIT = 2
    with pytest.raises(ValidationError):
        reply(thread, a, body="")
    with pytest.raises(ValidationError, match="Too many"):
        reply(thread, a)


def test_announcement_snapshot_is_named_not_dynamic(client, household):
    manager, a, b, lease = household
    notice = publish(draft(manager, properties=[lease.unit.property]), manager)
    assert notice.recipients.count() == 2
    newcomer = make_tenant(username="new")
    LeaseTenant.objects.create(lease=lease, tenant=newcomer)
    assert not Announcement.objects.visible_to(newcomer).exists()
    assert Announcement.objects.visible_to(b).filter(pk=notice.pk).exists()
    client.force_login(a)
    page = client.get(reverse("tenant_communications:announcement", args=[notice.public_id]))
    assert b"Recorded recipients" not in page.content
    assert client.get(reverse("tenant_communications:announcements")).status_code == 200
    assert Notification.objects.filter(version__announcement=notice).count() == 0
    thread = services.announcement_followup(notice, actor=a, lease=lease)
    assert thread.visibility == "PRIVATE"
    assert not Conversation.objects.visible_to(b).filter(pk=thread.pk).exists()
    assert services.announcement_followup(notice, actor=a, lease=lease).pk == thread.pk


def test_stale_publication_corrections_withdrawal_and_retry(household):
    manager, a, _, lease = household
    notice = draft(manager, important=True)
    token, _ = services.review_announcement(
        notice, actor=manager, title=notice.title, body=notice.body, important=True, expires_at=None
    )
    stranger = make_tenant(username="other")
    make_lease(make_unit(), tenants=[stranger])
    with pytest.raises(ValidationError, match="changed"):
        services.publish_announcement(actor=manager, review=token, portal_base="http://testserver")
    assert not notice.versions.exists()
    notice = publish(notice, manager)
    assert notice.recipients.filter(user=a, lease=lease).exists()
    original = notice.latest
    publish(notice, manager, title="Correction", reason="Updated time")
    assert notice.versions.count() == 2
    original.refresh_from_db()
    assert original.title == "Water service"
    before = notice.recipients.count()
    services.withdraw_announcement(notice, actor=manager, reason="No longer needed")
    assert Announcement.objects.visible_to(a).filter(pk=notice.pk).exists()
    assert notice.recipients.count() == before


def test_important_email_is_after_commit_neutral_and_no_repeat(
    household, django_capture_on_commit_callbacks, mailoutbox
):
    manager, a, b, _ = household
    with django_capture_on_commit_callbacks(execute=True):
        message = start(a, household[3], visibility="SHARED", body="Private body never emailed")
    assert len(mailoutbox) == 2
    assert all("Private body" not in item.body for item in mailoutbox)
    assert {item.to[0] for item in mailoutbox} == {manager.email, b.email}
    notices = list(Notification.objects.filter(message=message))
    for notice in notices:
        delivery.deliver(notice.pk)
    assert len(mailoutbox) == 2
    with django_capture_on_commit_callbacks(execute=True):
        notice = publish(draft(manager, important=True), manager)
    assert Notification.objects.filter(version__announcement=notice, status="SENT").count() == 2


def test_delivery_failure_and_explicit_ambiguous_retry(
    household, django_capture_on_commit_callbacks
):
    manager, a, _, lease = household
    with (
        patch(
            "apps.communications.delivery.send_mail", side_effect=RuntimeError("synthetic failure")
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        message = start(a, lease)
    notice = Notification.objects.get(message=message, recipient=manager)
    assert notice.status == "UNKNOWN"
    assert Message.objects.filter(pk=message.pk).exists()
    with pytest.raises(ValidationError):
        delivery.retry(notice, actor=manager)
    with django_capture_on_commit_callbacks(execute=True):
        delivery.retry(notice, actor=manager, acknowledge_duplicate=True)
    notice.refresh_from_db()
    assert notice.status == "SENT"


def test_notification_revoked_access_skips(household, mailoutbox):
    manager, a, _, lease = household
    message = start(a, lease)
    notice = Notification.objects.get(message=message, recipient=manager)
    manager.is_active = False
    manager.save()
    delivery.deliver(notice.pk)
    notice.refresh_from_db()
    assert notice.status == "SKIPPED"
    assert not mailoutbox


def test_real_form_workflow_read_receipt_and_escaping(client, household):
    _, a, _, lease = household
    client.force_login(a)
    new = reverse("tenant_communications:new")
    response = client.post(new, {"lease": lease.pk, "subject": "A topic", "visibility": "PRIVATE"})
    assert response.status_code == 200
    assert not Message.objects.exists()
    token = response.context["review"]
    response = client.post(
        new, {"review": token, "body": "<script>alert(1)</script>", "token": uuid4()}
    )
    assert response.status_code == 302
    page = client.get(response.url)
    assert b"&lt;script&gt;" in page.content
    assert not ReadPosition.objects.exists()
    row = Conversation.objects.get()
    read_url = reverse("tenant_communications:read", args=[row.public_id])
    assert client.post(read_url, {"receipt": "forged"}).status_code == 404
    assert client.post(read_url, {"receipt": page.context["read_receipt"]}).status_code == 302
    assert ReadPosition.objects.get(user=a).message_id == Message.objects.get().pk
    assert client.get(reverse("tenant_communications:index")).status_code == 200


def test_draft_and_publication_forms(client, household):
    manager, _, _, _ = household
    client.force_login(manager)
    result = client.post(
        reverse("communications:draft-new"), {"title": "Office closed", "body": "Holiday hours"}
    )
    assert result.status_code == 302
    notice = Announcement.objects.get()
    preview = client.post(
        reverse("communications:publish", args=[notice.public_id]),
        {"title": notice.title, "body": notice.body},
    )
    assert preview.status_code == 200
    assert not AnnouncementRecipient.objects.exists()
    review = preview.context["review"]
    assert (
        client.post(
            reverse("communications:publish", args=[notice.public_id]), {"review": review}
        ).status_code
        == 302
    )
    assert (
        client.post(
            reverse("communications:publish", args=[notice.public_id]), {"review": review}
        ).status_code
        == 302
    )
    assert AnnouncementVersion.objects.count() == 1


def test_partial_upload_failure_cleans_storage(household, settings):
    _, a, _, lease = household
    thread = start(a, lease).conversation
    before = Message.objects.count()
    with (
        patch.object(Attachment, "save", side_effect=RuntimeError("synthetic storage failure")),
        pytest.raises(RuntimeError),
    ):
        reply(thread, a, files=[SimpleUploadedFile("test.pdf", b"%PDF")])
    assert Message.objects.count() == before
    assert not list(settings.MEDIA_ROOT.rglob("*.pdf"))


def test_inactive_sender_and_future_tenancy_are_rejected(household):
    manager, a, _, lease = household
    thread = start(a, lease).conversation
    User.objects.filter(pk=a.pk).update(is_active=False)
    with pytest.raises(PermissionDenied):
        reply(thread, a)  # stale actor object must not bypass the locked authorization check
    lease.start_date = timezone.localdate() + timedelta(days=10)
    lease.save()
    with pytest.raises(ValidationError, match="before"):
        start(manager, lease, tenant=a, followup=True, reason="Premature follow-up")


def test_conversation_identity_cannot_be_retargeted(household):
    _, a, _, lease = household
    thread = start(a, lease).conversation
    thread.lease = make_lease(make_unit())
    with pytest.raises(ValidationError, match="identity"):
        thread.save()


def test_dashboard_counts_and_filter_privacy(client, household):
    manager, a, b, lease = household
    thread = start(a, lease).conversation
    client.force_login(manager)
    dashboard = client.get(reverse("manage:home"))
    assert dashboard.context["communications"]["needs_reply"] == 1
    assert dashboard.context["communications"]["unread"] == 1
    client.force_login(b)
    assert client.get(reverse("accounts:home")).context["communications"]["unread"] == 0
    url = reverse("tenant_communications:index")
    assert thread.subject not in client.get(url, {"tenant": a.pk}).content.decode()
    assert client.get(url, {"property": "forged"}).status_code == 404
    assert client.get(url, {"property": "²"}).status_code == 404
    assert client.get(url, {"unit": "9" * 100}).status_code == 404
    worker = make_maintenance()
    client.force_login(worker)
    assert not client.get(reverse("manage:home")).context["communications"]


def test_polling_receipts_only_acknowledge_rendered_messages(client, household):
    manager, a, b, lease = household
    first = start(a, lease)
    reply(first.conversation, manager)
    client.force_login(a)
    url = reverse("tenant_communications:updates", args=[first.conversation.public_id])
    response = client.get(url, {"after": first.pk})
    assert response.status_code == 200
    assert not ReadPosition.objects.exists()
    assert response.context["last_id"] > first.pk
    other = start(b, lease)
    assert client.get(url, {"after": other.pk}).status_code == 404
    client.force_login(b)
    assert client.get(url).status_code == 404


def test_known_failed_delivery_can_retry_without_duplicate_ack(
    household, django_capture_on_commit_callbacks
):
    manager, a, _, lease = household
    with (
        patch("apps.communications.delivery.send_mail", return_value=0),
        django_capture_on_commit_callbacks(execute=True),
    ):
        message = start(a, lease)
    notice = Notification.objects.get(message=message, recipient=manager)
    assert notice.status == "FAILED"
    with django_capture_on_commit_callbacks(execute=True):
        delivery.retry(notice, actor=manager)
    notice.refresh_from_db()
    assert notice.status == "SENT"


def test_expired_and_withdrawn_notices_are_history_not_active(client, household):
    manager, a, _, _ = household
    notice = publish(draft(manager), manager, expires_at=timezone.now() + timedelta(hours=1))
    client.force_login(a)
    url = reverse("tenant_communications:announcements")
    with patch(
        "apps.communications.views.timezone.now", return_value=timezone.now() + timedelta(days=1)
    ):
        assert notice.title not in client.get(url).content.decode()
        assert notice.title in client.get(url, {"archive": "1"}).content.decode()
    services.withdraw_announcement(notice, actor=manager, reason="Synthetic withdrawal")
    assert notice.title in client.get(url, {"archive": "1"}).content.decode()


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_sends_and_read_positions(household):
    from django.db import connections

    _, a, _, lease = household
    thread = start(a, lease).conversation
    token = uuid4()

    def send():
        try:
            actor = User.objects.get(pk=a.pk)
            return reply(Conversation.objects.get(pk=thread.pk), actor, token=token).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: send(), range(2)))
    assert ids[0] == ids[1]
    assert Message.objects.filter(author=a, token=token).count() == 1
    messages = list(thread.messages.all())

    def read(message_id):
        try:
            services.mark_read(thread, actor=User.objects.get(pk=a.pk), message_id=message_id)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(read, [messages[-1].pk, messages[0].pk]))
    assert ReadPosition.objects.get(user=a, conversation=thread).message_id == messages[-1].pk


@pytest.mark.django_db(transaction=True)
def test_concurrent_publication_is_idempotent(household):
    from django.db import connections

    manager, _, _, _ = household
    notice = draft(manager)
    review, _ = services.review_announcement(
        notice,
        actor=manager,
        title=notice.title,
        body=notice.body,
        important=False,
        expires_at=None,
    )

    def send(_):
        try:
            return services.publish_announcement(
                actor=User.objects.get(pk=manager.pk),
                review=review,
                portal_base="http://testserver",
            ).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(send, range(2))) == [notice.pk, notice.pk]
    assert notice.versions.count() == 1


@pytest.mark.django_db(transaction=True)
def test_cotenants_can_send_concurrently_without_notification_lock_deadlock(household):
    from django.db import connections

    _, a, b, lease = household
    thread = start(a, lease, visibility="SHARED").conversation

    def send(pk):
        try:
            return reply(thread, User.objects.get(pk=pk), body=f"Reply {pk}").pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(send, [a.pk, b.pk]))
    assert len(set(ids)) == 2
    assert thread.messages.count() == 3
