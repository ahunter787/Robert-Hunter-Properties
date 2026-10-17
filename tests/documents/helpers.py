"""Builders for the documents tests.

Deliberately not fixtures: a test says which actor and which attachment it needs by
calling these, and the shape of the row it is asserting against stays visible in the
test rather than hidden in a conftest.
"""

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.models import Document, DocumentCategory
from apps.documents.services import upload_document


def upload(name: str = "signed-lease.pdf", body: bytes = b"%PDF-1.4 lease") -> SimpleUploadedFile:
    """A file as a browser sends it: with a name and a content type."""
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def make_document(
    *,
    title: str = "Signed lease",
    category: str = DocumentCategory.LEASE,
    file_name: str = "signed-lease.pdf",
    body: bytes = b"%PDF-1.4 lease",
    lease=None,
    property=None,
    tenant=None,
    tenant_visible: bool = False,
    note: str = "",
    actor=None,
    document_date=None,
) -> Document:
    """A stored document row, with its bytes written through the service.

    Going through ``upload_document`` rather than ``Document.objects.create`` keeps
    every test row in the state the application itself produces (randomised storage
    name, ``original_name`` remembered, property filled in from the lease).
    """
    return upload_document(
        title=title,
        category=category,
        file=upload(file_name, body),
        lease=lease,
        property=property,
        tenant=tenant,
        tenant_visible=tenant_visible,
        note=note,
        actor=actor,
        document_date=document_date,
    )
