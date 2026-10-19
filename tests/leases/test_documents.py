"""A lease's documents, on the pages that show a tenancy.

The lease no longer owns a file (ADR-022): it owns a set of documents, and every one
of them is filed through the documents app. These tests hold the seams between the two
— the tenancy's page lists what is filed against it, the tenant sees only what was
shared, and both downloads are named after the document rather than its storage path.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.documents.models import Document, DocumentCategory
from tests.documents.helpers import make_document
from tests.factories import make_admin, make_lease, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="lease-document-manager"))
    return client


def a_tenancy(*, username: str = "ada", identifier: str = "1"):
    tenant = make_tenant(username=username)
    return tenant, make_lease(make_unit(identifier=identifier), tenants=[tenant])


def test_the_tenancys_page_lists_what_is_filed_against_it(as_manager):
    _, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, category=DocumentCategory.LEASE)
    make_document(title="November notice", lease=lease, category=DocumentCategory.NOTICE)

    body = as_manager.get(
        reverse("leases:lease-detail", args=[lease.pk]), {"section": "documents"}
    ).content.decode()

    assert "Signed lease" in body
    assert "November notice" in body
    assert "Lease" in body
    assert reverse("documents:upload") in body


def test_the_tenancys_page_marks_which_documents_the_tenant_can_see(as_manager):
    _, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, tenant_visible=True)
    make_document(title="Internal valuation", lease=lease, tenant_visible=False)

    body = as_manager.get(
        reverse("leases:lease-detail", args=[lease.pk]), {"section": "documents"}
    ).content.decode()

    assert "The tenant can see it" in body
    assert "Office only" in body


def test_the_tenancys_page_says_so_when_nothing_is_filed(as_manager):
    _, lease = a_tenancy()

    body = as_manager.get(
        reverse("leases:lease-detail", args=[lease.pk]), {"section": "documents"}
    ).content.decode()

    assert "Nothing filed against this tenancy yet" in body


def test_the_document_has_its_own_place_on_the_page_not_the_storage_path(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, file_name="scan-0001.pdf")

    body = as_manager.get(
        reverse("leases:lease-detail", args=[lease.pk]), {"section": "documents"}
    ).content.decode()

    assert reverse("documents:download", args=[document.pk]) in body
    assert document.file.name not in body, "the private path is never shown"


def test_the_officer_opens_the_document_the_page_links_to(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    body = b"".join(response.streaming_content)
    response.close()
    assert body.startswith(b"%PDF")


def test_the_tenancy_page_offers_the_tenants_documents_page(client):
    tenant, _ = a_tenancy()
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert reverse("tenant_documents:list") in body
    assert "Your documents" in body


def test_the_tenant_sees_the_lease_that_was_shared_with_them(client):
    tenant, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, tenant_visible=True)
    client.force_login(tenant)

    body = client.get(reverse("tenant_documents:list")).content.decode()

    assert "Signed lease" in body
    assert reverse("tenant_documents:download", args=[Document.objects.get().pk]) in body


def test_the_tenant_does_not_see_the_office_only_documents(client):
    tenant, lease = a_tenancy()
    make_document(title="Signed lease", lease=lease, tenant_visible=True)
    make_document(title="Internal valuation", lease=lease, tenant_visible=False)
    client.force_login(tenant)

    body = client.get(reverse("tenant_documents:list")).content.decode()

    assert "Signed lease" in body
    assert "Internal valuation" not in body


def test_the_tenants_documents_page_says_so_when_nothing_has_been_shared(client):
    tenant, _ = a_tenancy()
    client.force_login(tenant)

    body = client.get(reverse("tenant_documents:list")).content.decode()

    assert "Nothing has been shared with you yet" in body


def test_the_tenant_download_is_named_after_the_document_not_the_path(client):
    tenant, lease = a_tenancy()
    document = make_document(
        title="Signed lease November 2024.pdf",
        lease=lease,
        tenant_visible=True,
        file_name="scan-0001.pdf",
    )
    client.force_login(tenant)

    response = client.get(reverse("tenant_documents:download", args=[document.pk]))

    disposition = response["Content-Disposition"]
    assert 'filename="Signed lease November 2024.pdf"' in disposition
    assert document.file.name not in disposition
    assert "scan-0001" not in disposition
    response.close()


def test_a_lease_document_whose_bytes_are_missing_is_a_404_for_the_office(as_manager, settings):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)
    (settings.MEDIA_ROOT / document.file.name).unlink()

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 404
    assert Document.objects.filter(pk=document.pk).exists()


def test_a_lease_document_whose_bytes_are_missing_is_a_404_for_the_tenant(client, settings):
    tenant, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    (settings.MEDIA_ROOT / document.file.name).unlink()
    client.force_login(tenant)

    response = client.get(reverse("tenant_documents:download", args=[document.pk]))

    assert response.status_code == 404


def test_an_admin_files_a_document_from_the_tenancys_page(client):
    """The page's own button files against that tenancy, without asking again."""
    _, lease = a_tenancy()
    client.force_login(make_admin(username="lease-document-admin"))

    response = client.post(
        reverse("documents:upload") + f"?lease={lease.pk}",
        {
            "title": "Signed lease",
            "category": DocumentCategory.LEASE,
            "file": SimpleUploadedFile(
                "scan.pdf", b"%PDF-1.4 lease", content_type="application/pdf"
            ),
            "tenant_visible": "on",
        },
    )

    assert response.status_code == 302
    document = Document.objects.get()
    assert document.lease == lease
    assert document.property == lease.unit.property
    assert document.tenant_visible is True
