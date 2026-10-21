"""Uploading and removing a document, so the rules live in one place (ADR-022).

The views decide *who* is asking; this decides what happens, and writes the audit
event that makes either act legible afterwards.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.files import validate_document_upload
from apps.documents.models import Document


def _actor(actor):
    """The signed-in person behind an act, or None for a system write."""
    return actor if getattr(actor, "is_authenticated", False) else None


@transaction.atomic
def upload_document(
    *,
    title: str,
    category: str,
    file,
    lease=None,
    property=None,
    tenant=None,
    tenant_visible: bool = False,
    document_date=None,
    note: str = "",
    actor=None,
) -> Document:
    """File one uploaded document, and record who filed it.

    The upload rules are checked here as well as in the form: a screen is not the only
    caller, and a rule that only a form enforces is a rule a script can break.
    """
    validate_document_upload(file, max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024)
    document = Document(
        title=title.strip()[:200] or (file.name if file else "Document"),
        category=category,
        file=file,
        lease=lease,
        property=property,
        tenant=tenant,
        tenant_visible=bool(tenant_visible),
        document_date=document_date,
        note=note.strip(),
        uploaded_by=_actor(actor),
    )
    document.clean()
    document.save()

    record(
        _actor(actor),
        AuditAction.DOCUMENT_UPLOADED,
        obj=document,
        lease=lease,
        summary=(
            f"Document uploaded: {document.title} ({document.get_category_display()}) — "
            f"{'tenant can see it' if document.tenant_visible else 'staff only'}"
        ),
        category=category,
        attached_to=document.attachment_label,
        tenant_visible=document.tenant_visible,
        original_name=document.original_name,
    )
    return document


@transaction.atomic
def remove_document(document: Document, *, note: str, actor=None) -> None:
    """Remove a document uploaded in error — the row and the stored file.

    An admin's act, with a reason (P6-Q4). The bytes go, because a file known to be
    wrong has no business sitting in storage; the audit event stays, and it carries
    everything the row said — its title, category, what it was attached to, and who
    removed it and why.
    """
    if not note.strip():
        raise ValidationError({"note": "Say why this document is being removed."})

    from apps.leases.models import LeaseOpeningRecord

    if LeaseOpeningRecord.objects.filter(evidence=document).exists():
        raise ValidationError(
            "This document supports an immutable starting record and must be retained. "
            "Record a correction instead of removing its evidence."
        )

    summary = (
        f"Document removed: {document.title} ({document.get_category_display()}) — "
        f"{document.attachment_label}: {note.strip()}"
    )
    metadata = {
        "category": document.category,
        "attached_to": document.attachment_label,
        "tenant_visible": document.tenant_visible,
        "original_name": document.original_name,
        "document_date": document.document_date,
        "uploaded_by": document.uploaded_by.username if document.uploaded_by else None,
        "uploaded_at": document.created_at.isoformat() if document.created_at else None,
        "note": note.strip(),
    }
    lease = document.lease
    document_id = document.pk

    # The file first: if storage refuses, the row must not vanish with the file left
    # behind and no way to find it.
    if document.file:
        document.file.delete(save=False)
    document.delete()

    record(
        _actor(actor),
        AuditAction.DOCUMENT_REMOVED,
        obj=None,
        lease=lease,
        summary=summary,
        document_id=document_id,
        **metadata,
    )
