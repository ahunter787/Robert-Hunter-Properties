"""Proof-of-insurance intake and a manager decision; no screening or sales."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ProofStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted — pending manager review"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"


class TenantState(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    MISSING = "MISSING", "Missing"
    SUBMITTED = "SUBMITTED", "Submitted — pending manager review"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"


class InsuranceProof(models.Model):
    """One submitted proof. Append-only; the manager decision is a one-time transition."""

    lease = models.ForeignKey(
        "leases.Lease", on_delete=models.PROTECT, related_name="insurance_proofs"
    )
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT, related_name="insurance_proofs"
    )
    policy_start = models.DateField(null=True, blank=True)
    policy_end = models.DateField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=12, choices=ProofStatus.choices, default=ProofStatus.SUBMITTED
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="insurance_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    replaces = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replaced_by",
    )

    class Meta:
        ordering = ("-submitted_at", "-pk")

    def __str__(self):
        return f"Insurance proof #{self.pk} for lease {self.lease_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.get(pk=self.pk)
            if stored.status != ProofStatus.SUBMITTED:
                if any(
                    getattr(self, field) != getattr(stored, field)
                    for field in (
                        "lease_id",
                        "document_id",
                        "policy_start",
                        "policy_end",
                        "submitted_by_id",
                        "status",
                        "reviewed_by_id",
                        "reviewed_at",
                        "review_note",
                        "replaces_id",
                    )
                ):
                    raise ValidationError("A reviewed insurance proof is immutable.")
            elif self.status not in ProofStatus.values:
                raise ValidationError("Choose a valid insurance decision.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Insurance proof history is retained.")
