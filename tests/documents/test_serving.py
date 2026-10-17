"""Serving a document: the application does it, not the web server.

Every download goes through a permission-checked view, is marked private and is named
for a person rather than by its storage path (ADR-022). A row whose bytes have gone
answers 404 rather than a 500 from the storage backend, and nothing under `/media/`
is reachable through a Django URL.
"""

import sys
from urllib.parse import quote

import pytest
from django.test.utils import override_settings
from django.urls import reverse, set_urlconf

from apps.common.files import DOCUMENT_EXTENSIONS
from apps.documents.models import Document
from apps.documents.services import upload_document
from tests.documents.helpers import make_document, upload
from tests.factories import make_lease, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="serving-manager"))
    return client


@pytest.fixture
def as_tenant(client):
    return client


def a_tenancy(*, username: str = "ada"):
    tenant = make_tenant(username=username)
    return tenant, make_lease(make_unit(), tenants=[tenant])


def test_a_download_is_private_and_not_sniffable(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 200
    assert "private" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    response.close()


def test_the_download_is_named_after_the_title_not_the_storage_path(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, file_name="scan-0001.pdf")

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    disposition = response["Content-Disposition"]
    assert 'filename="Signed lease.pdf"' == disposition.split("; ")[-1]
    assert "scan-0001" not in disposition
    assert document.file.name not in disposition
    response.close()


def test_a_title_that_is_not_a_filename_gains_the_stored_suffix(as_manager):
    """A title a person chose opens as a file their machine recognises."""
    _, lease = a_tenancy()
    document = make_document(title="November inspection", lease=lease, file_name="scan.pdf")

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert 'filename="November inspection.pdf"' in response["Content-Disposition"]
    response.close()


def test_a_title_with_characters_a_filename_cannot_carry_is_rfc_5987_encoded(as_manager):
    """The readable name still reaches the browser, encoded the way HTTP requires."""
    _, lease = a_tenancy()
    document = make_document(
        title="Signed lease \u2013 November 2024.pdf", lease=lease, file_name="scan.pdf"
    )

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert quote("Signed lease \u2013 November 2024.pdf") in response["Content-Disposition"]
    assert document.file.name not in response["Content-Disposition"]
    response.close()


def test_a_title_that_already_names_the_extension_is_not_doubled(as_manager):
    _, lease = a_tenancy()
    document = make_document(title="Nov 2024 scan.pdf", lease=lease, file_name="scan.pdf")

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert "scan.pdf.pdf" not in response["Content-Disposition"]
    response.close()


def test_a_document_whose_bytes_are_missing_is_a_404_not_a_500(as_manager, settings):
    """A restore that missed media must not break the screen that opens it."""
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)
    (settings.MEDIA_ROOT / document.file.name).unlink()

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert response.status_code == 404
    assert Document.objects.filter(pk=document.pk).exists(), "the row is still the office's"


def test_the_tenants_copy_disappears_once_the_bytes_are_gone(as_tenant, settings):
    tenant, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    (settings.MEDIA_ROOT / document.file.name).unlink()
    as_tenant.force_login(tenant)

    response = as_tenant.get(reverse("tenant_documents:download", args=[document.pk]))

    assert response.status_code == 404


def test_the_tenant_download_is_named_after_the_title_too(as_tenant):
    tenant, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    as_tenant.force_login(tenant)

    response = as_tenant.get(reverse("tenant_documents:download", args=[document.pk]))

    assert response.status_code == 200
    assert 'filename="Signed lease.pdf"' in response["Content-Disposition"]
    assert document.file.name not in response["Content-Disposition"]
    response.close()


def test_the_bytes_are_only_reachable_through_the_view(as_manager, settings):
    """The application's view answers; the storage path is not a way in."""
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)

    assert document.file.name.startswith("documents/")
    assert "Signed lease" not in document.file.name
    assert (settings.MEDIA_ROOT / document.file.name).exists()
    response = as_manager.get(reverse("documents:download", args=[document.pk]))
    assert response.status_code == 200
    response.close()


def test_the_pdf_body_is_streamed_unchanged(as_manager):
    body = b"%PDF-1.4 the actual lease bytes"
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease, body=body)

    response = as_manager.get(reverse("documents:download", args=[document.pk]))

    assert b"".join(response.streaming_content) == body
    response.close()


def test_nothing_under_media_is_reachable_with_debug_off(settings):
    """Production serves no media: the web server and the proxy never touch it.

    `config/urls.py` adds the static route only under `DEBUG`, and the test run has
    `DEBUG` on, so the URLconf is re-imported with it off — the state production
    boots in — and the request is handed to that resolver.
    """
    _, lease = a_tenancy()
    document = make_document(title="Signed lease", lease=lease)
    stored = settings.MEDIA_ROOT / document.file.name
    assert stored.exists(), "the file is on disk; the point is that no URL reaches it"

    from django.test import Client

    module = sys.modules.pop("config.urls", None)
    try:
        with override_settings(DEBUG=False):
            set_urlconf(None)
            response = Client().get(f"{settings.MEDIA_URL}{document.file.name}")
    finally:
        if module is not None:
            sys.modules["config.urls"] = module
        set_urlconf(None)

    assert response.status_code == 404


def test_the_upload_allow_list_is_the_one_the_common_module_declares():
    """The storage extension comes from the upload, not from the title."""
    _, lease = a_tenancy()
    document = upload_document(
        title="Nothing like a filename",
        category="OTHER",
        file=upload("statement.csv", body=b"a,b\n1,2\n"),
        lease=lease,
    )

    assert ".csv" in DOCUMENT_EXTENSIONS
    assert document.file.name.endswith(".csv")
