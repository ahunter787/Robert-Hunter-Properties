"""The tenant's own lease area — the first page a tenant sees with real data."""

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.leases.models import LeaseStatus
from tests.factories import make_lease, make_tenant, make_unit

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def attach_document(lease, name="signed-lease.pdf"):
    lease.lease_file.save(
        name, SimpleUploadedFile(name, b"%PDF-1.4 lease", content_type="application/pdf")
    )
    return lease.lease_file.name


def test_a_tenant_sees_their_current_lease(client):
    tenant = make_tenant(username="ada", first_name="Ada", last_name="One")
    make_lease(make_unit(identifier="Storefront"), tenants=[tenant])
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Storefront" in body
    assert "Lease term" in body
    assert "$1,850.00" in body
    assert "1st of every month" in body
    assert "Ada One" in body


def test_the_tenant_page_shows_the_other_people_on_the_lease(client):
    ada = make_tenant(username="ada", first_name="Ada")
    ben = make_tenant(username="ben", first_name="Ben")
    make_lease(make_unit(), tenants=[ada, ben])
    client.force_login(ada)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "Ada" in body
    assert "Ben" in body
    assert "Primary contact" in body


def test_a_tenant_without_a_lease_sees_an_empty_state(client):
    client.force_login(make_tenant(username="new-tenant"))

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "No lease yet" in body
    assert "contact Robert Hunter Properties" in body


def test_an_ended_lease_is_still_shown_to_the_tenant(client):
    tenant = make_tenant(username="former")
    make_lease(
        make_unit(),
        tenants=[tenant],
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=40),
    )
    client.force_login(tenant)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "This lease ended on" in body


def test_a_tenant_only_ever_sees_their_own_lease(client):
    mine = make_tenant(username="mine", first_name="Mine")
    theirs = make_tenant(username="theirs", first_name="Theirs")
    make_lease(make_unit(identifier="MyUnit"), tenants=[mine])
    make_lease(make_unit(identifier="TheirUnit"), tenants=[theirs])
    client.force_login(mine)

    body = client.get(reverse("tenancy:lease")).content.decode()

    assert "MyUnit" in body
    assert "TheirUnit" not in body
    assert "Theirs" not in body


def test_a_tenant_with_no_lease_has_no_document(client):
    client.force_login(make_tenant(username="new-tenant"))

    assert client.get(reverse("tenancy:document")).status_code == 404


def test_the_lease_document_is_served_to_the_tenant_on_it(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(make_unit(), tenants=[tenant])
    attach_document(lease)
    client.force_login(tenant)

    response = client.get(reverse("tenancy:document"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["X-Content-Type-Options"] == "nosniff"
    body = b"".join(response.streaming_content)
    response.close()
    assert body.startswith(b"%PDF")


def test_a_tenant_without_a_document_gets_a_404(client):
    tenant = make_tenant(username="ada")
    make_lease(make_unit(), tenants=[tenant])
    client.force_login(tenant)

    assert client.get(reverse("tenancy:document")).status_code == 404


def test_another_tenants_document_is_unreachable(client):
    """There is no id in the tenant URL, so there is nothing to guess."""
    mine = make_tenant(username="mine")
    theirs = make_tenant(username="theirs")
    make_lease(make_unit(identifier="Mine"), tenants=[mine])
    their_lease = make_lease(make_unit(identifier="Theirs"), tenants=[theirs])
    attach_document(their_lease)
    client.force_login(mine)

    response = client.get(reverse("tenancy:document"))

    assert response.status_code == 404


def test_the_lease_page_offers_the_document_only_when_there_is_one(client):
    tenant = make_tenant(username="ada")
    lease = make_lease(make_unit(), tenants=[tenant])

    client.force_login(tenant)
    assert "View your lease" not in client.get(reverse("tenancy:lease")).content.decode()

    attach_document(lease)
    assert "View your lease" in client.get(reverse("tenancy:lease")).content.decode()


def test_the_tenant_navigation_offers_the_lease_page(client):
    client.force_login(make_tenant(username="ada"))

    body = client.get(reverse("accounts:profile")).content.decode()

    assert reverse("tenancy:lease") in body


def test_staff_navigation_offers_the_lease_desk(client):
    from tests.factories import make_manager

    client.force_login(make_manager(username="lease-manager"))

    body = client.get(reverse("manage:home")).content.decode()

    assert reverse("leases:lease-list") in body
