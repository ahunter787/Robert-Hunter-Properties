"""Durable after-commit emails. SMTP acceptance is not proof of reading."""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MANAGER_ROLES, User

from .models import Announcement, Conversation, Notification, NotificationAttempt


def _queue(*, recipient, portal_url, message=None, version=None):
    notice, created = Notification.objects.get_or_create(
        recipient=recipient, message=message, version=version, defaults={"portal_url": portal_url}
    )
    if created:
        transaction.on_commit(lambda pk=notice.pk: deliver(pk), robust=True)


def queue_message(message, portal_base):
    conversation = message.conversation
    users = User.objects.filter(pk__in=conversation.participants.values("user_id"))
    if message.author.is_tenant:
        users = User.objects.filter(pk__in=users.values("pk")) | User.objects.filter(
            role__in=MANAGER_ROLES
        )
    for user in users.filter(is_active=True).exclude(pk=message.author_id).distinct():
        namespace = "tenant_communications" if user.is_tenant else "communications"
        url = portal_base.rstrip("/") + reverse(
            f"{namespace}:conversation", args=[conversation.public_id]
        )
        _queue(recipient=user, portal_url=url, message=message)


def queue_announcement(version, portal_base):
    ids = version.announcement.recipients.values("user_id")
    for user in User.objects.filter(pk__in=ids, is_active=True).exclude(pk=version.author_id):
        url = portal_base.rstrip("/") + reverse(
            "tenant_communications:announcement", args=[version.announcement.public_id]
        )
        _queue(recipient=user, portal_url=url, version=version)


def _authorized(notice):
    user = notice.recipient
    if not user.is_active or not user.email:
        return False
    if notice.message_id:
        return (
            Conversation.objects.visible_to(user).filter(pk=notice.message.conversation_id).exists()
        )
    return Announcement.objects.visible_to(user).filter(pk=notice.version.announcement_id).exists()


def deliver(pk):
    # Commit intent BEFORE SMTP, so a process interruption cannot masquerade as a safe failure.
    with transaction.atomic():
        notice = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("recipient", "message__conversation", "version__announcement")
            .get(pk=pk)
        )
        if notice.status != "PENDING":
            return
        if not _authorized(notice):
            notice.status, notice.error = "SKIPPED", "Recipient has no access or email address."
            NotificationAttempt.objects.create(
                notification=notice, outcome="SKIPPED", detail=notice.error
            )
            notice.save(update_fields=["status", "error"])
            return
        notice.status, notice.started_at, notice.error = "SENDING", timezone.now(), ""
        notice.save(update_fields=["status", "started_at", "error"])
        NotificationAttempt.objects.create(notification=notice, outcome="STARTED")
    try:
        accepted = send_mail(
            "RHP communications update",
            "You have an RHP portal update. Sign in to view it:\n"
            + notice.portal_url
            + "\n\nPlease reply in the portal, not to this email. "
            "This is not an emergency service.",
            settings.DEFAULT_FROM_EMAIL,
            [notice.recipient.email],
        )
    except Exception:
        # An exception after SMTP DATA may mean the server accepted the message.
        status, error = "UNKNOWN", "Email outcome is uncertain. Retrying may send a duplicate."
    else:
        status, error = (
            ("SENT", "") if accepted else ("FAILED", "Mail backend did not accept the email.")
        )
    with transaction.atomic():
        notice = Notification.objects.select_for_update().get(pk=pk)
        notice.status, notice.error = status, error
        if status == "SENT":
            notice.sent_at = timezone.now()
        notice.save(update_fields=["status", "error", "sent_at"])
        NotificationAttempt.objects.create(notification=notice, outcome=status, detail=error)


@transaction.atomic
def retry(notice, *, actor, acknowledge_duplicate=False):
    from .services import authorize

    authorize(actor, manager=True)
    notice = Notification.objects.select_for_update().get(pk=notice.pk)
    if notice.status == "SENT":
        return
    if notice.status == "SENDING" and notice.started_at > timezone.now() - timedelta(minutes=5):
        raise ValidationError(
            "Delivery may still be running. Wait five minutes before reviewing it."
        )
    if notice.status in ("UNKNOWN", "SENDING") and not acknowledge_duplicate:
        raise ValidationError("Confirm that retrying an uncertain delivery may send a duplicate.")
    notice.status = "PENDING"
    notice.save(update_fields=["status"])
    transaction.on_commit(lambda: deliver(notice.pk), robust=True)
