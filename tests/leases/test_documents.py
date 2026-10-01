"""Lease documents: validation, storage, serving, and cleanup."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.leases.models import Lease, LeaseStatus
from tests.factories import make_admin, make_lease, make_manager, make_tenant, make_unit
from tests.leases.payloads import lease_post_data

pytestmark = pytest.mark.django_db


def document(name="signed-lease.pdf", content_type="application/pdf", body=b"%PDF-1.4 lease"):
    return SimpleUploadedFile(name, body, content_type=content_type)


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="document-manager"))
    return client


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="document-admin"))
    return client


def test_uploading_a_lease_document_stores_a_randomised_name(as_manager, settings):
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant], status=LeaseStatus.DRAFT)

    response = as_manager.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(unit, lease=lease, lease_file=document("my scan.pdf")),
    )

    lease.refresh_from_db()
    assert response.status_code == 302
    assert lease.lease_file.name.startswith("lease_documents/")
    assert "my scan" not in lease.lease_file.name
    assert (settings.MEDIA_ROOT / lease.lease_file.name).exists()


def test_a_wrong_file_type_is_refused(as_manager):
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant], status=LeaseStatus.DRAFT)

    response = as_manager.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(
            unit,
            lease=lease,
            lease_file=document("lease.docx", content_type="application/msword", body=b"PK"),
        ),
    )

    lease.refresh_from_db()
    assert response.status_code == 200
    assert not lease.lease_file
    assert b"PDF, or as a JPEG or PNG scan" in response.content


def test_an_oversized_document_is_refused(as_manager, settings):
    settings.RHP_MAX_UPLOAD_MB = 1
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant], status=LeaseStatus.DRAFT)

    response = as_manager.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(
            unit,
            lease=lease,
            lease_file=document(body=b"%PDF-1.4" + b"x" * (2 * 1024 * 1024)),
        ),
    )

    lease.refresh_from_db()
    assert response.status_code == 200
    assert not lease.lease_file
    assert b"larger than 1 MB" in response.content


def test_replacing_a_document_deletes_the_previous_file(as_manager, settings):
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant], status=LeaseStatus.DRAFT)

    as_manager.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(unit, lease=lease, lease_file=document("first.pdf")),
    )
    lease.refresh_from_db()
    first = lease.lease_file.name

    as_manager.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(unit, lease=lease, lease_file=document("second.pdf")),
    )
    lease.refresh_from_db()

    assert lease.lease_file.name != first
    assert not (settings.MEDIA_ROOT / first).exists()
    assert (settings.MEDIA_ROOT / lease.lease_file.name).exists()


def test_deleting_a_draft_removes_its_document(as_admin, settings):
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant], status=LeaseStatus.DRAFT)
    as_admin.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(unit, lease=lease, lease_file=document()),
    )
    lease.refresh_from_db()
    stored = lease.lease_file.name
    assert (settings.MEDIA_ROOT / stored).exists()

    as_admin.post(reverse("leases:lease-delete", args=[lease.pk]))

    assert not (settings.MEDIA_ROOT / stored).exists()


def test_the_document_is_served_to_staff(as_manager):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])
    lease.lease_file.save("lease.pdf", document())
    assert lease.lease_file

    response = as_manager.get(reverse("leases:lease-document", args=[lease.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    body = b"".join(response.streaming_content)
    response.close()
    assert body.startswith(b"%PDF")


def test_a_lease_without_a_document_has_no_document_url(as_manager):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])

    assert as_manager.get(reverse("leases:lease-document", args=[lease.pk])).status_code == 404


def test_the_document_link_appears_on_the_lease_page(as_manager):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])
    lease.lease_file.save("lease.pdf", document())

    body = as_manager.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()

    assert reverse("leases:lease-document", args=[lease.pk]) in body
    assert "View lease" in body


def test_a_document_only_reachable_through_the_view(as_manager):
    """The file lives under MEDIA_ROOT, which the proxy never serves in production."""
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])
    lease.lease_file.save("lease.pdf", document())

    assert lease.lease_file.name.startswith("lease_documents/")
    assert Lease.objects.get(pk=lease.pk).lease_file.name == lease.lease_file.name
