"""The office's side: everything they hold, and the two ways a file gets in.

A manager sees every document — including the ones a tenant never will — filters the
list the way a desk asks, and downloads any of them through a permission-checked view
rather than a storage path. What arrives is stored under a random name, with the name
the client sent kept on the row, and the act is recorded.
"""

import pytest
from django.urls import reverse

from apps.audit.models import AuditAction, AuditEvent
from apps.documents.models import Document, DocumentCategory
from tests.documents.helpers import make_document, upload
from tests.factories import make_lease, make_manager, make_property, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="document-manager"))
    return client


def a_tenancy(*, identifier: str = "1", username: str = "ada"):
    tenant = make_tenant(username=username)
    lease = make_lease(make_unit(identifier=identifier), tenants=[tenant])
    return tenant, lease


def test_a_manager_lists_every_document_including_the_hidden_ones(as_manager):
    _, lease = a_tenancy()
    shown = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    hidden = make_document(title="Internal valuation", lease=lease, tenant_visible=False)
    property_only = make_document(
        title="Roof survey",
        property=lease.unit.property,
        category=DocumentCategory.INSPECTION,
    )

    body = as_manager.get(reverse("documents:list")).content.decode()

    assert "Signed lease" in body
    assert "Internal valuation" in body
    assert "Roof survey" in body
    for document in (shown, hidden, property_only):
        assert reverse("documents:download", args=[document.pk]) in body


def test_a_property_only_document_is_reachable_to_staff(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Roof survey", property=lease.unit.property)

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 200
    response.close()
    assert "Roof survey" in response["Content-Disposition"]


def test_the_search_reads_the_title_the_note_and_the_name_it_arrived_with(as_manager):
    _, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, file_name="scan-0001.pdf")
    make_document(title="Boiler certificate", lease=lease, file_name="boiler.pdf")

    by_title = as_manager.get(reverse("documents:list"), {"q": "boiler"}).content.decode()
    assert "Boiler certificate" in by_title
    assert "Signed lease" not in by_title

    by_original_name = as_manager.get(
        reverse("documents:list"), {"q": "scan-0001"}
    ).content.decode()
    assert "Signed lease" in by_original_name
    assert "Boiler certificate" not in by_original_name


def test_the_category_filter_keeps_only_that_category(as_manager):
    _, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, category=DocumentCategory.LEASE)
    make_document(title="November notice", lease=lease, category=DocumentCategory.NOTICE)

    body = as_manager.get(
        reverse("documents:list"), {"category": DocumentCategory.NOTICE}
    ).content.decode()

    assert "November notice" in body
    assert "Signed lease" not in body


def test_the_visibility_filter_separates_the_tenants_copies_from_the_office_ones(as_manager):
    _, lease = a_tenancy()
    make_document(title="Shared notice", lease=lease, tenant_visible=True)
    make_document(title="Internal valuation", lease=lease, tenant_visible=False)

    tenant_side = as_manager.get(reverse("documents:list"), {"visibility": "tenant"}).content
    staff_side = as_manager.get(reverse("documents:list"), {"visibility": "staff"}).content

    assert b"Shared notice" in tenant_side
    assert b"Internal valuation" not in tenant_side
    assert b"Internal valuation" in staff_side
    assert b"Shared notice" not in staff_side


def test_the_property_filter_reads_the_property_a_document_was_filed_against(as_manager):
    _, mine = a_tenancy(identifier="Mine")
    _, theirs = a_tenancy(identifier="Theirs", username="ben")
    make_document(title="Mine lease", lease=mine)
    make_document(title="Theirs lease", lease=theirs)

    body = as_manager.get(
        reverse("documents:list"), {"property": mine.unit.property_id}
    ).content.decode()

    assert "Mine lease" in body
    assert "Theirs lease" not in body


def test_a_tenant_has_no_document_desk(client):
    """The office list is a whole-area refusal, not a scoped one."""
    client.force_login(make_tenant(username="plain-tenant"))

    assert client.get(reverse("documents:list")).status_code == 403
    assert client.get(reverse("documents:upload")).status_code == 403


def test_an_upload_records_who_filed_it_and_what_it_is(as_manager):
    _, lease = a_tenancy()
    manager = make_manager(username="filing-manager")
    as_manager.force_login(manager)
    response = as_manager.post(
        reverse("documents:upload"),
        {
            "title": "Signed lease",
            "category": DocumentCategory.LEASE,
            "file": upload("my scan.pdf"),
            "lease": lease.pk,
            "tenant_visible": "on",
            "note": "Filed at move-in.",
        },
    )

    assert response.status_code == 302
    document = Document.objects.get()
    assert document.lease == lease
    assert document.uploaded_by == manager
    event = AuditEvent.objects.get(action=AuditAction.DOCUMENT_UPLOADED)
    assert event.actor == manager
    assert event.lease == lease
    assert event.metadata["category"] == DocumentCategory.LEASE
    assert event.metadata["tenant_visible"] is True
    assert "Signed lease" in event.summary


def test_the_stored_path_is_randomised_and_the_client_name_is_kept(as_manager, settings):
    _, lease = a_tenancy()

    response = as_manager.post(
        reverse("documents:upload"),
        {
            "title": "Signed lease",
            "category": DocumentCategory.LEASE,
            "file": upload("Michael Ortolano Lease (Nov 2024).pdf"),
            "lease": lease.pk,
        },
    )

    assert response.status_code == 302
    document = Document.objects.get()
    assert document.original_name == "Michael Ortolano Lease (Nov 2024).pdf"
    assert document.file.name.startswith("documents/")
    assert "Michael Ortolano" not in document.file.name
    assert document.file.name.endswith(".pdf")
    assert (settings.MEDIA_ROOT / document.file.name).exists()


def test_an_upload_against_a_tenancy_is_filed_against_its_property_too(as_manager):
    _, lease = a_tenancy()

    as_manager.post(
        reverse("documents:upload"),
        {
            "title": "Signed lease",
            "category": DocumentCategory.LEASE,
            "file": upload(),
            "lease": lease.pk,
        },
    )

    document = Document.objects.get()
    assert document.property == lease.unit.property


def test_a_manager_may_download_any_document(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, tenant_visible=False)

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 200
    body = b"".join(response.streaming_content)
    response.close()
    assert body.startswith(b"%PDF")


def test_a_property_document_may_not_be_filed_as_tenant_visible(as_manager):
    """A property-only document has nobody to show it to; the view refuses it."""
    property_ = make_property()

    response = as_manager.post(
        reverse("documents:upload") + f"?property={property_.pk}",
        {
            "title": "Roof survey",
            "category": DocumentCategory.INSPECTION,
            "file": upload(),
            "tenant_visible": "on",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert not Document.objects.exists()
    assert b"no tenant to show it to" in response.content
