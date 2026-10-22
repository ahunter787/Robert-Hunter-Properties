"""Authorized transactional communications; money and maintenance are not touched."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.services import record
from apps.common.files import validate_document_upload
from apps.common.images import validate_image_upload
from apps.leases.models import Lease

from .models import (
    Announcement,
    AnnouncementRecipient,
    AnnouncementVersion,
    Attachment,
    Conversation,
    ConversationPreference,
    Event,
    InternalNote,
    Message,
    Participant,
    ReadPosition,
    SendAttempt,
)

SALT = "rhp.communications.review.v1"


def authorize(actor, *, manager=False):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or not (actor.is_manager_or_above or (actor.is_tenant and not manager))
    ):
        raise PermissionDenied


def members(lease):
    return sorted(
        lease.lease_tenants.filter(tenant__role=Role.TENANT).values_list("tenant_id", flat=True)
    )


def current(lease):
    return Lease.objects.current().filter(pk=lease.pk).exists()


def can_send(conversation, actor):
    if not Conversation.objects.visible_to(actor).filter(pk=conversation.pk).exists():
        return False
    if conversation.frozen_at:
        return False
    ids = members(conversation.lease)
    if conversation.visibility == "SHARED" and ids != conversation.household:
        return False
    participants = set(conversation.participants.values_list("user_id", flat=True))
    return conversation.followup_enabled or (
        current(conversation.lease) and participants <= set(ids)
    )


def event(obj, actor, kind, reason):
    field = "conversation" if isinstance(obj, Conversation) else "announcement"
    Event.objects.create(**{field: obj}, actor=actor, kind=kind, reason=reason)
    record(actor, "COMMUNICATION_CHANGED", obj=obj, summary=reason[:255], kind=kind)


@transaction.atomic
def freeze_household(lease_id):
    lease = Lease.objects.select_for_update().filter(pk=lease_id).first()
    if not lease:
        return
    ids = members(lease)
    for row in Conversation.objects.select_for_update().filter(
        lease=lease, visibility="SHARED", frozen_at=None
    ):
        if ids != row.household:
            row.frozen_at = timezone.now()
            row.freeze_reason = "The tenancy's participants changed. Start a new conversation."
            row.save(update_fields=["frozen_at", "freeze_reason"])
            event(row, None, "FROZEN", row.freeze_reason)


def _load_review(token, actor, kind):
    try:
        data = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as error:
        raise ValidationError(
            "This review expired or changed. Review the recipients again."
        ) from error
    if data.get("actor") != actor.pk or data.get("kind") != kind:
        raise ValidationError("This review does not belong to this action.")
    return data


def review_conversation(
    *, actor, lease, subject, visibility, tenant=None, followup=False, reason=""
):
    authorize(actor)
    subject = subject.strip()
    if not subject or len(subject) > 160 or visibility not in Conversation.Visibility.values:
        raise ValidationError("Enter a subject and choose private or tenancy-shared.")
    ids = members(lease)
    if lease.status == "DRAFT":
        raise ValidationError("A draft lease cannot receive messages.")
    if actor.is_tenant and (actor.pk not in ids or not current(lease) or followup):
        raise PermissionDenied
    if not current(lease) and not followup:
        raise ValidationError(
            "This tenancy is not current. A manager must allow messages after move-out."
        )
    if followup:
        authorize(actor, manager=True)
        if lease.start_date > timezone.localdate():
            raise ValidationError("Messages cannot be allowed before the tenancy begins.")
        if not reason.strip() or visibility != "PRIVATE":
            raise ValidationError("Choose one former tenant and explain why messages are needed.")
    if visibility == "PRIVATE":
        target = actor if actor.is_tenant else tenant
        permitted = set(ids)
        if followup:
            permitted.update(
                Participant.objects.filter(conversation__lease=lease).values_list(
                    "user_id", flat=True
                )
            )
        if not target or not target.is_tenant or target.pk not in permitted:
            raise ValidationError("Choose a tenant associated with this tenancy.")
        selected = [target.pk]
    else:
        selected = ids
    if not selected:
        raise ValidationError("No tenant participants are available.")
    data = {
        "kind": "conversation",
        "actor": actor.pk,
        "lease": lease.pk,
        "unit": lease.unit_id,
        "subject": subject,
        "visibility": visibility,
        "participants": selected,
        "household": ids,
        "followup": followup,
        "reason": reason.strip(),
    }
    return signing.dumps(data, salt=SALT), data


def conversation_review(token, actor):
    authorize(actor)
    return _load_review(token, actor, "conversation")


def validate_files(files):
    if len(files) > 10:
        raise ValidationError("Attach at most ten files to a message.")
    for upload in files:
        if Path(upload.name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise ValidationError("Attach JPEG, PNG or WebP photos, or PDF documents.")
        validate_document_upload(
            upload,
            max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024,
            allowed={".jpg", ".jpeg", ".png", ".webp", ".pdf"},
        )
        if not upload.name.lower().endswith(".pdf"):
            validate_image_upload(upload, max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024)


def _fingerprint(context, body, files):
    if len(body) > 10000 or (not body.strip() and not files):
        raise ValidationError("Enter a message of up to 10,000 characters or attach a file.")
    validate_files(files)
    hashes = []
    for upload in files:
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        hashes.append([upload.name, digest.hexdigest()])
    return hashlib.sha256(
        json.dumps([context, body.strip(), hashes], sort_keys=True).encode()
    ).hexdigest()


def _attempt(actor):
    authorize(actor)
    with transaction.atomic():
        User.objects.select_for_update(no_key=True).get(pk=actor.pk)
        since = timezone.now() - timedelta(minutes=5)
        limit = settings.RHP_COMMUNICATION_SEND_LIMIT
        if SendAttempt.objects.filter(user=actor, created_at__gte=since).count() >= limit:
            raise ValidationError(
                "Too many send attempts. Wait five minutes and try again.", code="rate_limit"
            )
        SendAttempt.objects.create(user=actor)


def _existing(actor, token, fingerprint):
    try:
        token = UUID(str(token))
    except ValueError as error:
        raise ValidationError("The send token is invalid. Reload the conversation.") from error
    row = Message.objects.filter(author=actor, token=token).select_related("conversation").first()
    if row:
        if row.fingerprint != fingerprint:
            raise ValidationError(
                "This send was already used with different content. Reload before sending again."
            )
        if not Conversation.objects.visible_to(actor).filter(pk=row.conversation_id).exists():
            raise PermissionDenied
    return row


def _write_message(conversation, actor, body, files, token, fingerprint, stored, portal_base):
    if not can_send(conversation, actor):
        raise ValidationError(
            "This conversation is read-only. Contact RHP to ask whether messages can be allowed."
        )
    message = Message.objects.create(
        conversation=conversation,
        author=actor,
        body=body.strip(),
        token=token,
        fingerprint=fingerprint,
    )
    for upload in files:
        attachment = Attachment(message=message, display_name=upload.name[:255])
        attachment.file.save(upload.name, upload, save=False)
        stored.append((attachment.file.name, attachment.file.storage))
        attachment.save()
    conversation.state = "NEEDS_RHP" if actor.is_tenant else "WAITING"
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["state", "updated_at"])
    from .delivery import queue_message

    queue_message(message, portal_base)
    record(
        actor,
        "COMMUNICATION_CHANGED",
        obj=conversation,
        summary="Message sent.",
        message=message.pk,
    )
    return message


def _clean_files(stored):
    for name, storage in stored:
        if not Attachment.objects.filter(file=name).exists():
            storage.delete(name)


def start_conversation(*, actor, review, body, files, token, portal_base):
    _attempt(actor)
    data = conversation_review(review, actor)
    fp = _fingerprint(data, body, files)
    stored = []
    try:
        with transaction.atomic():
            actor = User.objects.select_for_update(no_key=True).get(pk=actor.pk)
            authorize(actor)
            if row := _existing(actor, token, fp):
                return row
            lease = Lease.objects.select_for_update().get(pk=data["lease"])
            if lease.unit_id != data["unit"] or members(lease) != data["household"]:
                raise ValidationError(
                    "The tenancy changed since review. Review participants again."
                )
            _, validated = review_conversation(
                actor=actor,
                lease=lease,
                subject=data["subject"],
                visibility=data["visibility"],
                tenant=User.objects.filter(pk=data["participants"][0]).first(),
                followup=data["followup"],
                reason=data["reason"],
            )
            if validated != data:
                raise ValidationError("The reviewed participants changed. Review again.")
            conversation = Conversation.objects.create(
                lease=lease,
                subject=data["subject"],
                visibility=data["visibility"],
                created_by=actor,
                household=data["household"],
                followup_enabled=data["followup"],
            )
            for pk in data["participants"]:
                Participant.objects.create(conversation=conversation, user_id=pk)
            if data["followup"]:
                event(conversation, actor, "FOLLOWUP_ENABLED", data["reason"])
            return _write_message(conversation, actor, body, files, token, fp, stored, portal_base)
    except Exception:
        _clean_files(stored)
        raise


def send_message(conversation, *, actor, body, files, token, portal_base):
    _attempt(actor)
    if not Conversation.objects.visible_to(actor).filter(pk=conversation.pk).exists():
        raise PermissionDenied
    fp = _fingerprint({"conversation": conversation.pk}, body, files)
    stored = []
    try:
        with transaction.atomic():
            actor = User.objects.select_for_update(no_key=True).get(pk=actor.pk)
            authorize(actor)
            if row := _existing(actor, token, fp):
                return row
            Lease.objects.select_for_update().get(pk=conversation.lease_id)
            conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
            return _write_message(conversation, actor, body, files, token, fp, stored, portal_base)
    except Exception:
        _clean_files(stored)
        raise


@transaction.atomic
def mark_read(conversation, *, actor, message_id):
    authorize(actor)
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation.pk, pk__in=Conversation.objects.visible_to(actor).values("pk")
    )
    message = Message.objects.get(pk=message_id, conversation=conversation)
    position, created = ReadPosition.objects.get_or_create(
        conversation=conversation, user=actor, defaults={"message": message}
    )
    if not created and position.message_id < message.pk:
        position.message = message
        position.save(update_fields=["message"])


@transaction.atomic
def change_work(conversation, *, actor, action, reason=""):
    authorize(actor, manager=True)
    Lease.objects.select_for_update().get(pk=conversation.lease_id)
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    if action in ("enable-followup", "disable-followup"):
        if not reason.strip():
            raise ValidationError(
                "Explain why messages after move-out are being allowed or turned off."
            )
        if conversation.frozen_at and action == "enable-followup":
            raise ValidationError(
                "The tenant list changed, so this conversation stays read-only. "
                "Start a new private conversation instead."
            )
        if action == "enable-followup" and conversation.lease.start_date > timezone.localdate():
            raise ValidationError("Messages cannot be allowed before the tenancy begins.")
        conversation.followup_enabled = action == "enable-followup"
        conversation.save(update_fields=["followup_enabled"])
    elif action == "handled":
        conversation.state = "HANDLED"
        conversation.save(update_fields=["state"])
        reason = reason.strip() or "Marked handled by RHP."
    else:
        raise ValidationError("Choose an available conversation action.")
    event(conversation, actor, action.upper(), reason.strip())


def _notice_data(title, body, important, expires_at):
    if not title.strip() or len(title) > 160 or not body.strip() or len(body) > 10000:
        raise ValidationError("Enter a title and announcement of up to 10,000 characters.")
    if expires_at and expires_at <= timezone.now():
        raise ValidationError("Choose an expiration in the future.")
    return {
        "title": title.strip(),
        "body": body.strip(),
        "important": bool(important),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@transaction.atomic
def save_draft(*, actor, title, body, important, expires_at, properties, announcement=None):
    authorize(actor, manager=True)
    _notice_data(title, body, important, expires_at)
    if announcement:
        announcement = Announcement.objects.select_for_update(no_key=True).get(pk=announcement.pk)
        if announcement.published_at:
            raise ValidationError(
                "Publish a correction instead of editing a published announcement."
            )
    else:
        announcement = Announcement(created_by=actor)
    announcement.title, announcement.body = title.strip(), body.strip()
    announcement.important, announcement.expires_at = important, expires_at
    announcement.property_ids = sorted(p.pk for p in properties)
    announcement.save()
    return announcement


def recipients(announcement):
    if announcement.published_at:
        return sorted(announcement.recipients.values_list("lease_id", "user_id"))
    leases = Lease.objects.current()
    if announcement.property_ids:
        leases = leases.filter(unit__property_id__in=announcement.property_ids)
    return sorted(
        set(
            leases.filter(lease_tenants__tenant__role=Role.TENANT).values_list(
                "pk", "lease_tenants__tenant_id"
            )
        )
    )


def review_announcement(announcement, *, actor, title, body, important, expires_at, reason=""):
    authorize(actor, manager=True)
    announcement.refresh_from_db()
    if announcement.withdrawn_at:
        raise ValidationError("Withdrawn announcements cannot be republished.")
    if announcement.published_at and not reason.strip():
        raise ValidationError("Explain this correction.")
    content = _notice_data(title, body, important, expires_at)
    audience = recipients(announcement)
    if not audience:
        raise ValidationError("No current tenant recipients match this announcement.")
    data = {
        "kind": "announcement",
        "actor": actor.pk,
        "pk": announcement.pk,
        "updated": announcement.updated_at.isoformat(),
        "version": announcement.latest.pk if announcement.latest else None,
        "audience": audience,
        "content": content,
        "reason": reason.strip(),
    }
    return signing.dumps(data, salt=SALT), data


def announcement_review(token, actor):
    authorize(actor, manager=True)
    return _load_review(token, actor, "announcement")


@transaction.atomic
def publish_announcement(*, actor, review, portal_base):
    data = announcement_review(review, actor)
    review_key = hashlib.sha256(review.encode()).hexdigest()
    if existing := AnnouncementVersion.objects.filter(review_key=review_key).first():
        return existing.announcement
    announcement = Announcement.objects.select_for_update(no_key=True).get(pk=data["pk"])
    if existing := AnnouncementVersion.objects.filter(review_key=review_key).first():
        return existing.announcement
    # Serialize every current tenancy against sends/membership and end-of-tenancy writes.
    list(
        Lease.objects.select_for_update()
        .filter(pk__in=[p[0] for p in data["audience"]])
        .order_by("pk")
    )
    latest = announcement.latest
    audience = [list(pair) for pair in recipients(announcement)]
    if (
        announcement.withdrawn_at
        or announcement.updated_at.isoformat() != data["updated"]
        or (latest.pk if latest else None) != data["version"]
        or audience != data["audience"]
    ):
        raise ValidationError(
            "The announcement or recipients changed. Review before publishing again."
        )
    content = data["content"]
    from django.utils.dateparse import parse_datetime

    expiry = parse_datetime(content["expires_at"]) if content["expires_at"] else None
    _notice_data(content["title"], content["body"], content["important"], expiry)
    if not announcement.published_at:
        announcement.published_at = timezone.now()
        announcement.save(update_fields=["published_at", "updated_at"])
        for lease_id, user_id in audience:
            AnnouncementRecipient.objects.create(
                announcement=announcement, lease_id=lease_id, user_id=user_id
            )
    else:
        announcement.save(update_fields=["updated_at"])
    version = AnnouncementVersion.objects.create(
        announcement=announcement,
        title=content["title"],
        body=content["body"],
        important=content["important"],
        expires_at=expiry,
        author=actor,
        reason=data["reason"],
        review_key=review_key,
    )
    event(
        announcement,
        actor,
        "PUBLISHED" if not latest else "CORRECTED",
        data["reason"] or "Announcement published.",
    )
    from .delivery import queue_announcement

    if version.important:
        queue_announcement(version, portal_base)
    return announcement


@transaction.atomic
def withdraw_announcement(announcement, *, actor, reason):
    authorize(actor, manager=True)
    if not reason.strip():
        raise ValidationError("Explain why this announcement is being withdrawn.")
    announcement = Announcement.objects.select_for_update(no_key=True).get(pk=announcement.pk)
    if not announcement.published_at or announcement.withdrawn_at:
        raise ValidationError("Only a published, current announcement can be withdrawn.")
    announcement.withdrawn_at = timezone.now()
    announcement.save(update_fields=["withdrawn_at", "updated_at"])
    event(announcement, actor, "WITHDRAWN", reason.strip())


@transaction.atomic
def announcement_followup(announcement, *, actor, lease):
    authorize(actor)
    Lease.objects.select_for_update().get(pk=lease.pk)
    if not actor.is_tenant or not announcement.recipients.filter(user=actor, lease=lease).exists():
        raise PermissionDenied
    if not current(lease) or actor.pk not in members(lease):
        raise ValidationError(
            "This tenancy is read-only. Contact RHP to ask about further messages."
        )
    key = f"{announcement.pk}:{lease.pk}:{actor.pk}"
    conversation, created = Conversation.objects.get_or_create(
        origin_key=key,
        defaults={
            "origin": announcement,
            "lease": lease,
            "subject": f"About: {announcement.latest.title}"[:160],
            "visibility": "PRIVATE",
            "created_by": actor,
            "household": members(lease),
        },
    )
    if created:
        Participant.objects.create(conversation=conversation, user=actor)
    return conversation


@transaction.atomic
def set_preference(conversation, *, actor, archived=None, mute=None):
    """Per-user inbox state; never mutates shared history or authorization."""
    authorize(actor, manager=True)
    if not Conversation.objects.visible_to(actor).filter(pk=conversation.pk).exists():
        raise PermissionDenied
    preference, _ = ConversationPreference.objects.select_for_update().get_or_create(
        conversation=conversation, user=actor
    )
    if archived is not None:
        preference.archived_at = timezone.now() if archived else None
    if mute is not None:
        preference.mute_email = bool(mute)
    preference.save()
    record(
        actor,
        "COMMUNICATION_CHANGED",
        obj=conversation,
        summary="Conversation inbox preference changed.",
        archived=preference.archived_at.isoformat() if preference.archived_at else "",
        mute=preference.mute_email,
    )
    return preference


@transaction.atomic
def add_internal_note(conversation, *, actor, body):
    """Staff-only append-only note; never returned to a tenant."""
    authorize(actor, manager=True)
    if not Conversation.objects.visible_to(actor).filter(pk=conversation.pk).exists():
        raise PermissionDenied
    body = (body or "").strip()
    if not body or len(body) > 10000:
        raise ValidationError("Write a note of up to 10,000 characters.")
    note = InternalNote.objects.create(conversation=conversation, author=actor, body=body)
    record(
        actor,
        "COMMUNICATION_CHANGED",
        obj=conversation,
        summary="Internal note added.",
        note=note.pk,
    )
    return note
