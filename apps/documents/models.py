"""Documents: one row per file, whatever it is for (Phase 6, ADR-022).

The office keeps a signed lease, its addendum, a notice, an inspection photo and a
receipt against a tenancy, a property or a person. A `Document` is one file with a
category, a title a person reads, and — the only question that matters to a tenant —
whether they are allowed to see it.

Two rules hold everything together:

* **A tenant sees a document only when it is marked visible and belongs to their own
  tenancy.** The scope is the query, not a check afterwards (`visible_to`).
* **Nothing is served by its storage path.** Files are stored under a random name and
  every download goes through a permission-checked view (`apps/common/files.py`).
"""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property


def document_path(instance, filename: str) -> str:
    """Randomised storage path, remembering the name it arrived with.

    Never the client's filename: a stored name is not a way to reach a file
    (ADR-009, docs/security.md). The readable name is kept on the row instead, for
    the screen and for the download.
    """
    if not instance.original_name:
        instance.original_name = Path(filename.replace("\\", "/")).name[:255]
    suffix = Path(filename).suffix.lower()
    if len(suffix) > 10 or not suffix.isascii():
        suffix = ""
    return f"documents/{uuid4().hex}{suffix}"


class DocumentCategory(models.TextChoices):
    """The categories the specification names, in the order it names them."""

    LEASE = "LEASE", "Lease"
    ADDENDUM = "ADDENDUM", "Addendum"
    NOTICE = "NOTICE", "Notice"
    RECEIPT = "RECEIPT", "Receipt"
    INSPECTION = "INSPECTION", "Inspection"
    CORRESPONDENCE = "CORRESPONDENCE", "Correspondence"
    INSURANCE = "INSURANCE", "Renters insurance proof"
    OTHER = "OTHER", "Other"


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        """What this user may see as a tenant: visible, and their own tenancy.

        The authorization scope, in the query rather than in a check afterwards, so
        a caller cannot forget it and still get rows.
        """
        if not getattr(user, "is_authenticated", False):
            return self.none()
        return (
            self.filter(tenant_visible=True)
            .filter(Q(lease__lease_tenants__tenant=user) | Q(tenant=user))
            .distinct()
        )

    def for_staff(self):
        """The office's list: everything, newest first."""
        return self.select_related("lease__unit__property", "property", "tenant", "uploaded_by")


class Document(models.Model):
    """One uploaded file, and who is allowed to see it."""

    title = models.CharField(
        max_length=200,
        help_text="What a person calls it: 'Signed lease', 'November inspection'.",
    )
    category = models.CharField(
        max_length=16,
        choices=DocumentCategory.choices,
        default=DocumentCategory.OTHER,
        db_index=True,
    )
    file = models.FileField(upload_to=document_path, max_length=255)
    original_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="The name it was uploaded with. Kept for the record; never used to store it.",
    )

    # Where it belongs: at least one of these, and a tenancy is the usual answer.
    lease = models.ForeignKey(
        "leases.Lease",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )

    #: P6-Q1: staff-only unless somebody says otherwise, on purpose.
    tenant_visible = models.BooleanField(
        default=False,
        db_index=True,
        help_text="The tenant can open it on their own pages, and nobody else's.",
    )
    document_date = models.DateField(
        null=True, blank=True, help_text="The date on the document itself, if it has one."
    )
    note = models.TextField(blank=True, help_text="Office notes. Never shown to a tenant.")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            # The rule the tenant scope relies on, at the database: a document nobody
            # can be shown is not a visibly-tenant document (ADR-022, P6-Q1).
            models.CheckConstraint(
                condition=(
                    models.Q(tenant_visible=False)
                    | models.Q(lease__isnull=False)
                    | models.Q(tenant__isnull=False)
                ),
                name="visible_document_needs_a_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["category", "created_at"], name="document_category_created"),
            models.Index(fields=["tenant_visible", "created_at"], name="document_visible_created"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        # A tenancy's document belongs to that tenancy's property as well, so the
        # property's own screen can list it without a join through the lease.
        if self.lease_id and self.property_id is None:
            self.property_id = self.lease.unit.property_id
        super().save(*args, **kwargs)

    def clean(self):
        if self.lease_id is None and self.property_id is None and self.tenant_id is None:
            raise ValidationError(
                {
                    "lease": "File this against a tenancy, a property or a tenant — "
                    "a document nobody can reach is a document nobody can use."
                }
            )
        if self.tenant_visible and self.lease_id is None and self.tenant_id is None:
            raise ValidationError(
                {
                    "tenant_visible": "A property document has no tenant to show it to. "
                    "Attach it to a tenancy or a tenant first."
                }
            )

    # cached_property, not @property: the `property` field above shadows the decorator
    # inside this class body — the same reason Unit uses it (apps/properties/models.py).
    @cached_property
    def display_name(self) -> str:
        """What the download is called: the title, with the stored file's suffix."""
        return self.title

    @cached_property
    def attachment_label(self) -> str:
        """What it is filed against, in one phrase, for a list."""
        if self.lease_id:
            return f"Tenancy · {self.lease.unit.identifier}"
        if self.tenant_id:
            return f"Tenant · {self.tenant.get_full_name() or self.tenant.username}"
        if self.property_id:
            return f"Property · {self.property.name}"
        return "Unfiled"

    def is_visible_to(self, user) -> bool:
        """Whether this user may read it: the office, or the tenancy it belongs to."""
        if getattr(user, "is_manager_or_above", False):
            return True
        if not self.tenant_visible or not getattr(user, "is_authenticated", False):
            return False
        if self.tenant_id == user.pk:
            return True
        return bool(self.lease_id) and self.lease.lease_tenants.filter(tenant=user).exists()
