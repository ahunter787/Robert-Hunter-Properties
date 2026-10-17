"""The upload rules, at the form and at the service behind it.

A screen is not the only caller of `upload_document`, so the same rules are checked
in both places: a file type RHP does not take, a file too large, and a document with
no attachment at all are refused wherever they arrive.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.documents.forms import DocumentForm, DocumentRemoveForm
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import upload_document
from tests.documents.helpers import upload
from tests.factories import make_lease, make_property, make_tenant

pytestmark = pytest.mark.django_db


def a_tenancy():
    """A lease with a tenant on it, for the preset the screen would pass."""
    return make_lease(tenants=[make_tenant(username="ada")])


def form_data(**overrides):
    data = {"title": "Signed lease", "category": DocumentCategory.LEASE}
    data.update(overrides)
    return data


def test_a_disallowed_extension_is_refused():
    form = DocumentForm(form_data(), {"file": upload("contract.exe", body=b"MZ")})

    assert not form.is_valid()
    assert "file" in form.errors
    assert "PDFs" in form.errors["file"][0]


def test_the_service_refuses_the_same_file_the_form_does():
    """Anything that calls the service gets the same refusal, view or script."""
    with pytest.raises(ValidationError):
        upload_document(
            title="Contract",
            category=DocumentCategory.OTHER,
            file=upload("contract.exe", body=b"MZ"),
            lease=a_tenancy(),
        )

    assert not Document.objects.exists()


def test_an_oversized_document_is_refused(settings):
    settings.RHP_MAX_UPLOAD_MB = 1
    form = DocumentForm(
        form_data(),
        {"file": upload("huge.pdf", body=b"%PDF" + b"x" * (2 * 1024 * 1024))},
    )

    assert not form.is_valid()
    assert "larger than 1 MB" in form.errors["file"][0]


def test_a_document_with_no_attachment_is_refused():
    form = DocumentForm(form_data(), {})

    assert not form.is_valid()
    assert "file" in form.errors


def test_a_document_filed_against_nothing_is_refused_by_the_form():
    """A document nobody can reach is a document nobody can use."""
    form = DocumentForm(form_data(), {"file": upload()})

    assert not form.is_valid()
    assert "File this against a tenancy" in form.errors["title"][0]


def test_a_document_filed_against_nothing_is_refused_by_the_service():
    """The form is the screen; the rule is the service's."""
    with pytest.raises(ValidationError) as raised:
        upload_document(title="Unfiled", category=DocumentCategory.OTHER, file=upload())

    assert "lease" in raised.value.message_dict
    assert not Document.objects.exists()


def test_the_form_offers_every_attachment_when_the_screen_did_not_know_one():
    """The desk's own upload screen: the office chooses what it is about."""
    form = DocumentForm()

    assert {"lease", "property", "tenant"}.issubset(form.fields)


def test_a_preset_attachment_is_not_asked_for_again():
    """The tenancy page files against that tenancy; the form does not re-ask."""
    form = DocumentForm(lease=a_tenancy())

    assert "lease" not in form.fields
    assert "property" in form.fields
    assert "tenant" in form.fields


def test_the_property_screen_files_against_the_property():
    form = DocumentForm(property=make_property())

    assert "property" not in form.fields
    assert "lease" in form.fields


def test_the_tenant_screen_files_against_the_tenant():
    form = DocumentForm(tenant=make_tenant(username="ada"))

    assert "tenant" not in form.fields
    assert "lease" in form.fields


def test_a_property_document_cannot_be_made_tenant_visible():
    """There is no tenant on a property; the form refuses before the model has to."""
    form = DocumentForm(
        form_data(tenant_visible="on", property=make_property().pk),
        {"file": upload()},
    )

    assert not form.is_valid()
    assert "no tenant to show it to" in form.errors["tenant_visible"][0]


def test_a_tenant_visible_document_about_a_tenancy_is_allowed():
    lease = a_tenancy()
    form = DocumentForm(form_data(tenant_visible="on", lease=lease.pk), {"file": upload()})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["tenant_visible"] is True


def test_a_tenant_visible_document_about_a_tenant_is_allowed():
    tenant = make_tenant(username="ada")
    form = DocumentForm(form_data(tenant_visible="on", tenant=tenant.pk), {"file": upload()})

    assert form.is_valid(), form.errors


def test_a_preset_upload_is_validated_against_the_preset_the_screen_passed():
    """The popped attachment field must still reach the model the form validates.

    Otherwise `Document.clean()` refuses a document that *was* filed against a
    tenancy — and the model's error names a field the form has removed, which is a
    500 rather than a form error.
    """
    lease = a_tenancy()
    form = DocumentForm(form_data(), {"file": upload()}, lease=lease)

    assert form.is_valid(), form.errors
    assert form.instance.lease_id == lease.pk
    assert "lease" not in form.fields


def test_an_accepted_document_stores_the_client_name_off_the_path(settings):
    lease = a_tenancy()
    form = DocumentForm(form_data(lease=lease.pk), {"file": upload("Nov 2024 scan.pdf")})
    assert form.is_valid(), form.errors

    document = upload_document(
        title=form.cleaned_data["title"],
        category=form.cleaned_data["category"],
        file=form.cleaned_data["file"],
        lease=form.cleaned_data["lease"],
    )

    assert document.original_name == "Nov 2024 scan.pdf"
    assert document.file.name.startswith("documents/")
    assert "Nov 2024 scan" not in document.file.name
    assert (settings.MEDIA_ROOT / document.file.name).exists()


# --- the removal form -----------------------------------------------------


def test_removal_requires_a_reason():
    form = DocumentRemoveForm({"note": ""})

    assert not form.is_valid()
    assert "note" in form.errors


def test_removal_accepts_a_reason():
    form = DocumentRemoveForm({"note": "Wrong tenancy - re-filed against the right one."})

    assert form.is_valid(), form.errors
