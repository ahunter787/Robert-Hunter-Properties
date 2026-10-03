"""The audit trail: who changed what, and when.

Phase 4. A log line is not a record — it has no object the database knows about,
no actor it can join to, and it leaves with the log rotation. Anything that moves
money or changes a tenancy's status is appended here instead, in the same
transaction as the change itself, so a balance and the story of how it got there
can never disagree (ADR-008).

Events are append-only: they are never updated and never deleted.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditAction(models.TextChoices):
    LEASE_ACTIVATED = "LEASE_ACTIVATED", "Lease activated"
    LEASE_ENDED = "LEASE_ENDED", "Lease ended"
    RENT_SCHEDULE_GENERATED = "RENT_SCHEDULE_GENERATED", "Rent schedule generated"
    RENT_PERIOD_CHANGED = "RENT_PERIOD_CHANGED", "Rent period changed"
    NNN_RATE_SET = "NNN_RATE_SET", "NNN amount set"
    RESPONSIBILITY_CHANGED = "RESPONSIBILITY_CHANGED", "Responsibility changed"
    RESPONSIBILITY_CYCLE_STAGED = "RESPONSIBILITY_CYCLE_STAGED", "Responsibility cycle staged"
    RESPONSIBILITY_SHARES_SET = "RESPONSIBILITY_SHARES_SET", "Responsibility shares set"
    CHARGE_CREATED = "CHARGE_CREATED", "Charge created"
    CHARGE_ADJUSTED = "CHARGE_ADJUSTED", "Charge adjusted"
    PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment recorded"
    PAYMENT_CLEARED = "PAYMENT_CLEARED", "Payment cleared"
    PAYMENT_VOIDED = "PAYMENT_VOIDED", "Payment voided"
    PAYMENT_REVERSED = "PAYMENT_REVERSED", "Payment reversed"
    ROLE_CHANGED = "ROLE_CHANGED", "Role changed"


class AuditEventQuerySet(models.QuerySet):
    def for_lease(self, lease):
        """Everything recorded about one tenancy, newest first."""
        return self.filter(lease=lease)


class AuditEvent(models.Model):
    """One thing that happened, who did it, and to what."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        help_text="Null when the actor's account has since been removed.",
    )
    #: The tenancy this concerns, when there is one — the index the ledger reads.
    lease = models.ForeignKey(
        "leases.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices)
    object_type = models.CharField(
        max_length=64,
        blank=True,
        help_text='The model an event is about, as "app.Model".',
    )
    object_id = models.BigIntegerField(null=True, blank=True)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Small, JSON-safe facts about the event: amounts, dates, reasons.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_target"),
            models.Index(fields=["lease", "created_at"], name="audit_lease_created"),
            models.Index(fields=["action", "created_at"], name="audit_action_created"),
            models.Index(fields=["created_at"], name="audit_created"),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()}: {self.summary}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(
                "Audit events are append-only. Record a new event instead of changing this one."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are never deleted; they are the record.")
