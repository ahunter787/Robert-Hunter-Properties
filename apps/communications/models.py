"""Communications history is explicit, tenancy-scoped and independent of finances."""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("History is retained. Record a new entry.")

    def delete(self):
        raise ValidationError("History cannot be deleted.")


class Immutable(models.Model):
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("History is retained. Record a new entry.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("History cannot be deleted.")


class ConversationQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user.is_authenticated or not user.is_active:
            return self.none()
        if user.is_manager_or_above:
            return self.all()
        if user.is_tenant:
            return self.filter(participants__user=user).distinct()
        return self.none()


class Conversation(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE", "Private"
        SHARED = "SHARED", "Tenancy-shared"

    class State(models.TextChoices):
        NEEDS_RHP = "NEEDS_RHP", "Needs RHP reply"
        WAITING = "WAITING", "Waiting for tenant"
        HANDLED = "HANDLED", "Handled"

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    lease = models.ForeignKey("leases.Lease", on_delete=models.PROTECT)
    subject = models.CharField(max_length=160)
    visibility = models.CharField(max_length=8, choices=Visibility.choices)
    state = models.CharField(max_length=12, choices=State.choices, default=State.NEEDS_RHP)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    household = models.JSONField(default=list)
    frozen_at = models.DateTimeField(null=True, blank=True)
    freeze_reason = models.CharField(max_length=200, blank=True)
    followup_enabled = models.BooleanField(default=False)
    origin = models.ForeignKey("Announcement", null=True, blank=True, on_delete=models.PROTECT)
    origin_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    objects = ConversationQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-pk")

    def __str__(self):
        return self.subject

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = (
                "public_id",
                "lease_id",
                "subject",
                "visibility",
                "created_by_id",
                "household",
                "origin_id",
                "origin_key",
            )
            original = Conversation.objects.values(*fields).get(pk=self.pk)
            if any(original[field] != getattr(self, field) for field in fields):
                raise ValidationError("Conversation identity and audience cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Conversations are retained as history.")


class Participant(Immutable):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name="participants"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="comm_participant_unique")
        ]

    def __str__(self):
        return f"Participant #{self.pk}"


class Message(Immutable):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name="messages"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    token = models.UUIDField()
    fingerprint = models.CharField(max_length=64)

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.UniqueConstraint(fields=["author", "token"], name="comm_send_token_unique")
        ]

    def __str__(self):
        return f"Message #{self.pk}"


def attachment_path(instance, filename):
    return f"communications/{uuid4().hex}{Path(filename).suffix.lower()}"


class Attachment(Immutable):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    message = models.ForeignKey(Message, on_delete=models.PROTECT, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    display_name = models.CharField(max_length=255)

    def __str__(self):
        return self.display_name


class ReadPosition(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name="read_positions"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    message = models.ForeignKey(Message, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="comm_read_unique")
        ]

    def __str__(self):
        return f"Read position #{self.pk}"


class SendAttempt(Immutable):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Send attempt #{self.pk}"


class AnnouncementQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user.is_authenticated or not user.is_active:
            return self.none()
        if user.is_manager_or_above:
            return self.all()
        if user.is_tenant:
            return self.filter(recipients__user=user, published_at__isnull=False).distinct()
        return self.none()


class Announcement(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=160)
    body = models.TextField()
    important = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    property_ids = models.JSONField(default=list)
    published_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.published_at and any(
                getattr(old, f) != getattr(self, f)
                for f in (
                    "title",
                    "body",
                    "important",
                    "expires_at",
                    "property_ids",
                    "published_at",
                    "created_by_id",
                )
            ):
                raise ValidationError("Published notices are retained. Publish a correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Announcements are retained.")

    @property
    def latest(self):
        return self.versions.order_by("-pk").first()


class AnnouncementVersion(Immutable):
    announcement = models.ForeignKey(
        Announcement, on_delete=models.PROTECT, related_name="versions"
    )
    title = models.CharField(max_length=160)
    body = models.TextField()
    important = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    review_key = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return f"Announcement version #{self.pk}"


class AnnouncementRecipient(Immutable):
    announcement = models.ForeignKey(
        Announcement, on_delete=models.PROTECT, related_name="recipients"
    )
    lease = models.ForeignKey("leases.Lease", on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "lease", "user"], name="comm_notice_recipient_unique"
            )
        ]

    def __str__(self):
        return f"Announcement recipient #{self.pk}"


class Event(Immutable):
    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    announcement = models.ForeignKey(
        Announcement, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Communication event #{self.pk}"


class Notification(models.Model):
    message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.PROTECT)
    version = models.ForeignKey(
        AnnouncementVersion, null=True, blank=True, on_delete=models.PROTECT
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="communication_notifications",
    )
    portal_url = models.URLField(max_length=1000)
    status = models.CharField(max_length=12, default="PENDING")
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "recipient"], name="comm_message_notice_unique"
            ),
            models.UniqueConstraint(
                fields=["version", "recipient"], name="comm_version_notice_unique"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(message__isnull=False, version__isnull=True)
                    | models.Q(message__isnull=True, version__isnull=False)
                ),
                name="comm_notification_one_source",
            ),
        ]

    def __str__(self):
        return f"Communication email #{self.pk}"


class NotificationAttempt(Immutable):
    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name="attempts"
    )
    outcome = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)
    detail = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Email attempt #{self.pk}"
