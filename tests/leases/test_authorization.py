"""The lease role matrix, route by route."""

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.leases.models import LeaseStatus
from tests.factories import (
    make_admin,
    make_lease,
    make_maintenance,
    make_manager,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db


def a_lease(*, tenants=True, status=LeaseStatus.ACTIVE):
    """A lease with everything a lease page can show, including a document.

    Without a document the document route is a 404 for everyone (that case has
    its own test), which would make the matrix below assert the wrong thing.
    """
    lease = make_lease(
        make_unit(),
        status=status,
        tenants=[make_tenant(username="on-lease")] if tenants else (),
    )
    lease.lease_file.save("lease.pdf", ContentFile(b"%PDF-1.4 lease"))
    return lease


def lease_routes(lease):
    """Every lease page, except the document.

    The document streams a file, so its response has to be closed to release the
    handle; each test asserts it on its own line, last.
    """
    return [
        reverse("leases:lease-list"),
        reverse("leases:lease-create"),
        reverse("leases:lease-detail", args=[lease.pk]),
        reverse("leases:lease-update", args=[lease.pk]),
        reverse("leases:lease-delete", args=[lease.pk]),
    ]


def document_url(lease):
    return reverse("leases:lease-document", args=[lease.pk])


@pytest.mark.parametrize("maker", [make_tenant, make_maintenance], ids=["tenant", "maintenance"])
def test_roles_outside_leasing_are_forbidden(client, maker):
    lease = a_lease()
    client.force_login(maker(username=f"outsider-{maker.__name__}"))

    for url in lease_routes(lease):
        response = client.get(url)
        assert response.status_code == 403, f"{url} should be forbidden"
        assert b"403" in response.content

    assert client.get(document_url(lease)).status_code == 403
    assert client.post(reverse("leases:lease-activate", args=[lease.pk])).status_code == 403
    assert client.post(reverse("leases:lease-end", args=[lease.pk])).status_code == 403


def test_anonymous_visitors_are_sent_to_sign_in(client):
    lease = a_lease()

    for url in [*lease_routes(lease), document_url(lease)]:
        response = client.get(url)
        assert response.status_code == 302, f"{url} should redirect"
        assert reverse("accounts:login") in response["Location"]


def test_a_manager_runs_the_lease_desk_but_cannot_delete(client):
    lease = a_lease()
    client.force_login(make_manager(username="lease-manager"))

    assert client.get(reverse("leases:lease-list")).status_code == 200
    assert client.get(reverse("leases:lease-create")).status_code == 200
    assert client.get(reverse("leases:lease-detail", args=[lease.pk])).status_code == 200
    assert client.get(reverse("leases:lease-update", args=[lease.pk])).status_code == 200

    assert client.get(reverse("leases:lease-delete", args=[lease.pk])).status_code == 403
    assert client.post(reverse("leases:lease-delete", args=[lease.pk])).status_code == 403


def test_an_admin_may_reach_every_lease_page(client):
    # A draft, because for an activated lease the delete page is a redirect.
    lease = a_lease(status=LeaseStatus.DRAFT)
    client.force_login(make_admin(username="lease-admin"))

    for url in lease_routes(lease):
        assert client.get(url).status_code == 200, f"{url} should be reachable by an admin"

    document = client.get(document_url(lease))
    assert document.status_code == 200
    # Closing a response sends request_finished, which closes the test's database
    # connection, so this goes last.
    document.close()


def test_staff_are_turned_away_from_the_tenant_area(client):
    client.force_login(make_manager(username="lease-manager"))

    assert client.get(reverse("tenancy:lease")).status_code == 403
    assert client.get(reverse("tenancy:document")).status_code == 403


def test_a_tenant_is_turned_away_from_the_lease_desk(client):
    client.force_login(make_tenant(username="plain-tenant"))

    assert client.get(reverse("leases:lease-list")).status_code == 403
    assert client.get(reverse("manage:home")).status_code == 403
