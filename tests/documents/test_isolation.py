"""What a tenant may see, and what an id from somewhere else answers.

The non-negotiable of Phase 6: a tenant reads a document only when somebody marked
it visible **and** it belongs to their own tenancy. Anything else is a 404 — not a
403, which would confirm that the document exists — and never appears in a list.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.documents.models import Document, DocumentCategory
from tests.documents.helpers import make_document
from tests.factories import make_lease, make_manager, make_property, make_tenant, make_unit

pytestmark = pytest.mark.django_db


def tenancy(username: str, *, identifier: str = "1"):
    """A tenant, their lease, and the unit they live in."""
    tenant = make_tenant(username=username)
    lease = make_lease(make_unit(identifier=identifier), tenants=[tenant])
    return tenant, lease


def test_a_tenant_opens_a_document_shared_with_their_tenancy(client):
    tenant, lease = tenancy("ada")
    document = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    client.force_login(tenant)

    response = client.get(reverse("tenant_documents:download", args=[document.pk]))

    assert response.status_code == 200
    body = b"".join(response.streaming_content)
    response.close()
    assert body.startswith(b"%PDF")


def test_another_tenancys_document_id_is_a_404_not_a_refusal(client):
    """A 403 would admit the document exists; the answer must not name it."""
    ada, _ = tenancy("ada", identifier="Mine")
    ben, ben_lease = tenancy("ben", identifier="Theirs")
    theirs = make_document(title="Theirs", lease=ben_lease, tenant_visible=True)
    client.force_login(ada)

    response = client.get(reverse("tenant_documents:download", args=[theirs.pk]))

    assert response.status_code == 404
    assert b"Theirs" not in response.content


def test_another_tenancys_document_never_appears_in_the_tenants_list(client):
    ada, ada_lease = tenancy("ada", identifier="Mine")
    _, ben_lease = tenancy("ben", identifier="Theirs")
    mine = make_document(title="Mine", lease=ada_lease, tenant_visible=True)
    theirs = make_document(title="Theirs", lease=ben_lease, tenant_visible=True)
    client.force_login(ada)

    body = client.get(reverse("tenant_documents:list")).content.decode()

    assert "Mine" in body
    assert "Theirs" not in body
    assert theirs.pk not in list(Document.objects.visible_to(ada).values_list("pk", flat=True))
    assert mine.pk in list(Document.objects.visible_to(ada).values_list("pk", flat=True))


def test_a_hidden_document_is_a_404_for_the_tenancy_it_belongs_to(client):
    """`tenant_visible=False` is the office's filing cabinet, not the tenant's."""
    tenant, lease = tenancy("ada")
    hidden = make_document(title="Office note", lease=lease, tenant_visible=False)
    client.force_login(tenant)

    response = client.get(reverse("tenant_documents:download", args=[hidden.pk]))

    assert response.status_code == 404
    assert b"Office note" not in response.content


def test_a_hidden_document_of_their_own_tenancy_is_absent_from_the_list(client):
    tenant, lease = tenancy("ada")
    make_document(title="Visible notice", lease=lease, tenant_visible=True)
    make_document(title="Internal valuation", lease=lease, tenant_visible=False)
    client.force_login(tenant)

    body = client.get(reverse("tenant_documents:list")).content.decode()

    assert "Visible notice" in body
    assert "Internal valuation" not in body


def test_a_property_only_document_can_never_be_tenant_visible():
    """There is no tenant on a property, so there is nobody to show it to."""
    document = Document(
        title="Roof survey",
        category=DocumentCategory.INSPECTION,
        file="documents/roof.pdf",
        property=make_property(),
        tenant_visible=True,
    )

    with pytest.raises(ValidationError) as raised:
        document.full_clean()

    assert "tenant_visible" in raised.value.message_dict


def test_a_document_attached_to_a_tenant_directly_is_visible_to_them(client):
    """The other half of the scope: the tenant FK, with no tenancy in between."""
    tenant = make_tenant(username="ada")
    document = make_document(
        title="Your receipt", tenant=tenant, tenant_visible=True, category=DocumentCategory.RECEIPT
    )
    client.force_login(tenant)

    response = client.get(reverse("tenant_documents:download", args=[document.pk]))

    assert response.status_code == 200
    # Closing the streaming response releases the file handle; leave it open and the
    # next test's temporary directory complains.
    response.close()


def test_a_document_attached_to_another_tenant_is_not_visible(client):
    ada = make_tenant(username="ada")
    ben = make_tenant(username="ben")
    theirs = make_document(title="Ben's receipt", tenant=ben, tenant_visible=True)
    client.force_login(ada)

    assert client.get(reverse("tenant_documents:download", args=[theirs.pk])).status_code == 404


def test_the_scope_answers_for_itself_not_only_for_a_view():
    """`visible_to` is the authorization; a view that forgets it still gets nothing."""
    ada, ada_lease = tenancy("ada")
    _, ben_lease = tenancy("ben")
    mine = make_document(title="Mine", lease=ada_lease, tenant_visible=True)
    make_document(title="Theirs", lease=ben_lease, tenant_visible=True)
    make_document(title="Hidden", lease=ada_lease, tenant_visible=False)

    assert list(Document.objects.visible_to(ada)) == [mine]
    assert not Document.objects.visible_to(AnonymousUser()).exists()


def test_the_model_answers_the_same_way_as_the_queryset():
    ada, ada_lease = tenancy("ada")
    _, ben_lease = tenancy("ben")
    mine = make_document(title="Mine", lease=ada_lease, tenant_visible=True)
    hidden = make_document(title="Hidden", lease=ada_lease, tenant_visible=False)
    theirs = make_document(title="Theirs", lease=ben_lease, tenant_visible=True)

    assert mine.is_visible_to(ada)
    assert not hidden.is_visible_to(ada)
    assert not theirs.is_visible_to(ada)
    assert mine.is_visible_to(make_manager(username="document-manager"))


def test_a_tenant_cannot_reach_their_documents_through_the_office_urls(client):
    """The two surfaces stay apart: a tenant has no business in /manage/."""
    tenant, lease = tenancy("ada")
    document = make_document(title="Signed lease", lease=lease, tenant_visible=True)
    client.force_login(tenant)

    assert client.get(reverse("documents:list")).status_code == 403
    assert client.get(reverse("documents:download", args=[document.pk])).status_code == 403


def test_the_tenancy_page_links_to_the_tenants_documents(client):
    tenant, _ = tenancy("ada")
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert reverse("tenant_documents:list") in body


def test_a_document_filed_only_against_the_property_is_not_the_tenants():
    """The tenant lives there; the property's own file is still the office's."""
    tenant, lease = tenancy("ada")
    property_document = make_document(
        title="Roof survey", property=lease.unit.property, tenant_visible=False
    )

    assert property_document.lease_id is None
    assert not Document.objects.visible_to(tenant).filter(pk=property_document.pk).exists()
