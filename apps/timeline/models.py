"""Manual activity for the tenant timeline; system history stays in its source records."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class EntryKind(models.TextChoices):
    NOTE = "NOTE", "Note"
    TASK = "TASK", "Task"
    CALL = "CALL", "Call"
    MEETING = "MEETING", "Meeting"


class TimelineEntry(models.Model):
    lease = models.ForeignKey(
        "leases.Lease", on_delete=models.PROTECT, related_name="timeline_entries"
    )
    kind = models.CharField(max_length=10, choices=EntryKind.choices, default=EntryKind.NOTE)
    body = models.TextField(max_length=10000)
    occurred_at = models.DateTimeField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    visible_to_tenant = models.BooleanField(
        default=False,
        help_text="Share this manual entry on the tenant's own timeline.",
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("occurred_at", "pk")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(body=""), name="timeline_entry_body_required"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} on {self.lease_id}: {self.body[:40]}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Timeline entries are append-only; add a new entry.")
        if self.document_id and self.document.lease_id != self.lease_id:
            raise ValidationError("A timeline attachment must belong to the same tenancy.")
        if self.document_id and self.document.tenant_visible and not self.visible_to_tenant:
            raise ValidationError("A tenant-visible document implies a tenant-visible entry.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Timeline entries are never deleted.")
