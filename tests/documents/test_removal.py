"""Removing a document: an admin's act, with a reason, and what it leaves behind.

The rule the owner gave the phase: a document that should never have been filed is
deleted — the row *and* the bytes — by an admin, with a note that goes into the
history. A manager cannot do it, a note is not optional, and a superseded document is
not removed by any of this: the point of keeping it is the point of the rule.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.audit.models import AuditAction, AuditEvent
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import remove_document
from tests.documents.helpers import make_document, upload
from tests.factories import make_admin, make_lease, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="removal-manager"))
    return client


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="removal-admin"))
    return client


def a_tenancy(*, username: str = "ada"):
    tenant = make_tenant(username=username)
    return tenant, make_lease(make_unit(), tenants=[tenant])


def removal_url(document):
    return reverse("documents:remove", args=[document.pk])


def test_a_manager_is_refused_the_removal_screen(as_manager):
    """The manager files documents; taking one out of the record is an admin's."""
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    assert as_manager.get(removal_url(document)).status_code == 403
    assert as_manager.post(removal_url(document), {"note": "Wrong tenancy"}).status_code == 403
    assert Document.objects.filter(pk=document.pk).exists()


def test_an_admin_reaches_the_removal_screen(as_admin):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    body = as_admin.get(removal_url(document)).content.decode()

    assert "Signed lease" in body
    assert "Why it is being removed" in body


def test_the_note_is_required_and_nothing_is_removed_without_one(as_admin, settings):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)
    stored = settings.MEDIA_ROOT / document.file.name
    assert stored.exists()

    response = as_admin.post(removal_url(document), {"note": ""})

    assert response.status_code == 200
    assert Document.objects.filter(pk=document.pk).exists()
    assert stored.exists(), "a refused removal must not take the bytes with it"
    assert not AuditEvent.objects.filter(action=AuditAction.DOCUMENT_REMOVED).exists()


def test_removal_deletes_the_row_and_the_bytes(as_admin, settings):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)
    stored = settings.MEDIA_ROOT / document.file.name
    assert stored.exists()

    response = as_admin.post(removal_url(document), {"note": "Filed against the wrong tenancy."})

    assert response.status_code == 302
    assert not Document.objects.filter(pk=document.pk).exists()
    assert not stored.exists()


def test_removal_leaves_a_record_of_what_went(as_admin):
    tenant, lease = a_tenancy()
    document = make_document(
        title="November notice",
        category=DocumentCategory.NOTICE,
        lease=lease,
        tenant_visible=True,
        file_name="notice.pdf",
    )

    as_admin.post(removal_url(document), {"note": "Served on the wrong tenant."})

    event = AuditEvent.objects.get(action=AuditAction.DOCUMENT_REMOVED)
    assert event.actor.username == "removal-admin"
    assert event.lease == lease
    assert event.metadata["category"] == DocumentCategory.NOTICE
    assert event.metadata["note"] == "Served on the wrong tenant."
    assert event.metadata["tenant_visible"] is True
    assert event.metadata["document_id"] == document.pk
    assert "November notice" in event.summary
    assert "Notice" in event.summary
    assert "Served on the wrong tenant." in event.summary


def test_the_event_is_the_record_once_the_row_is_gone(as_admin):
    """The row is deleted, so the event cannot point at it; the summary is the story."""
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    as_admin.post(removal_url(document), {"note": "Uploaded in error."})

    event = AuditEvent.objects.get(action=AuditAction.DOCUMENT_REMOVED)
    assert event.object_id is None
    assert event.object_type == ""
    assert event.actor is not None
    assert not Document.objects.filter(pk=document.pk).exists()


def test_a_superseded_document_is_not_removed_by_filing_the_new_one(as_manager, settings):
    """Keeping the old version is the point: the new file sits beside it."""
    _, lease = a_tenancy()
    old = make_document(title="Signed lease 2023", lease=lease, file_name="2023.pdf")
    old_path = settings.MEDIA_ROOT / old.file.name

    as_manager.post(
        reverse("documents:upload"),
        {
            "title": "Signed lease 2024",
            "category": DocumentCategory.LEASE,
            "file": upload("2024.pdf"),
            "lease": lease.pk,
        },
    )

    assert Document.objects.filter(pk=old.pk).exists(), "the superseded copy stays"
    assert old_path.exists()
    assert Document.objects.count() == 2


def test_removing_one_document_leaves_the_other_rows_alone(as_admin, settings):
    _, lease = a_tenancy()
    wrong = make_document(title="Wrong upload", lease=lease)
    right = make_document(title="Signed lease", lease=lease, file_name="right.pdf")
    right_path = settings.MEDIA_ROOT / right.file.name

    as_admin.post(removal_url(wrong), {"note": "Uploaded in error."})

    assert Document.objects.filter(pk=right.pk).exists()
    assert right_path.exists()


def test_the_service_refuses_a_blank_note_even_outside_the_screen():
    """The view is one caller; the rule is the service's."""
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    with pytest.raises(ValidationError):
        remove_document(document, note="   ", actor=make_admin(username="service-admin"))

    assert Document.objects.filter(pk=document.pk).exists()
