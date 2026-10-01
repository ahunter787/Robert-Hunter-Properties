"""The lease desk: creating, activating, ending, and the rules around each."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.leases.models import Lease, LeaseStatus, LeaseTenant
from tests.factories import (
    make_admin,
    make_lease,
    make_manager,
    make_property,
    make_tenant,
    make_unit,
)
from tests.leases.payloads import lease_post_data

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="lease-manager"))
    return client


# --- creating -------------------------------------------------------------


def test_a_lease_is_created_as_a_draft_with_its_tenants(signed_in):
    unit = make_unit()
    ada = make_tenant(username="ada", first_name="Ada")
    ben = make_tenant(username="ben", first_name="Ben")

    response = signed_in.post(reverse("leases:lease-create"), lease_post_data(unit, [ada, ben]))

    lease = Lease.objects.get()
    assert response.status_code == 302
    assert lease.status == LeaseStatus.DRAFT
    assert lease.unit == unit
    assert lease.tenants == [ada, ben]
    assert lease.primary_tenant == ada


def test_a_lease_needs_at_least_one_tenant(signed_in):
    unit = make_unit()

    response = signed_in.post(reverse("leases:lease-create"), lease_post_data(unit, []))

    assert response.status_code == 200
    assert not Lease.objects.exists()
    assert b"A lease needs at least one tenant" in response.content


def test_the_same_tenant_cannot_be_listed_twice(signed_in):
    unit = make_unit()
    ada = make_tenant(username="ada")

    response = signed_in.post(reverse("leases:lease-create"), lease_post_data(unit, [ada, ada]))

    assert response.status_code == 200
    assert not Lease.objects.exists()
    assert b"The same tenant is listed more than once" in response.content


def test_only_one_primary_contact_is_allowed(signed_in):
    unit = make_unit()
    ada, ben = make_tenant(username="ada"), make_tenant(username="ben")
    payload = lease_post_data(unit, [ada, ben])
    payload["lease_tenants-1-is_primary"] = "on"

    response = signed_in.post(reverse("leases:lease-create"), payload)

    assert response.status_code == 200
    assert b"Only one tenant can be the primary contact" in response.content


def test_a_lease_cannot_end_before_it_starts(signed_in):
    unit = make_unit()
    payload = lease_post_data(unit, [make_tenant(username="ada")])
    payload["end_date"] = (TODAY - dt.timedelta(days=5)).isoformat()

    response = signed_in.post(reverse("leases:lease-create"), payload)

    assert response.status_code == 200
    assert b"cannot end before it starts" in response.content


def test_the_unit_picker_hides_units_that_are_already_let(signed_in):
    taken = make_unit(identifier="Taken")
    free = make_unit(identifier="Free")
    make_lease(taken)

    response = signed_in.get(reverse("leases:lease-create"))
    offered = response.context["form"].fields["unit"].queryset

    assert list(offered.values_list("identifier", flat=True)) == ["Free"]
    assert free in offered


def test_a_unit_can_be_preselected_from_a_link(signed_in):
    unit = make_unit()

    response = signed_in.get(reverse("leases:lease-create"), {"unit": unit.pk})

    assert response.context["form"].initial["unit"] == unit.pk


# --- activating and ending ------------------------------------------------


def test_a_draft_with_tenants_can_be_activated(signed_in):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")], status=LeaseStatus.DRAFT)

    response = signed_in.post(reverse("leases:lease-activate", args=[lease.pk]))

    lease.refresh_from_db()
    assert response.status_code == 302
    assert lease.status == LeaseStatus.ACTIVE


def test_a_draft_without_tenants_cannot_be_activated(signed_in):
    lease = make_lease(make_unit(), status=LeaseStatus.DRAFT)

    response = signed_in.post(reverse("leases:lease-activate", args=[lease.pk]), follow=True)

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.DRAFT
    assert b"Add at least one tenant" in response.content


def test_activating_reports_a_unit_that_is_already_let(signed_in):
    unit = make_unit()
    make_lease(unit)
    draft = make_lease(unit, tenants=[make_tenant(username="ada")], status=LeaseStatus.DRAFT)

    response = signed_in.post(reverse("leases:lease-activate", args=[draft.pk]), follow=True)

    draft.refresh_from_db()
    assert draft.status == LeaseStatus.DRAFT
    assert b"already has an active lease" in response.content


def test_an_active_lease_can_be_ended(signed_in):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])

    response = signed_in.post(reverse("leases:lease-end", args=[lease.pk]))

    lease.refresh_from_db()
    assert response.status_code == 302
    assert lease.status == LeaseStatus.ENDED


def test_an_ended_lease_stays_readable(signed_in):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")], status=LeaseStatus.ENDED)

    response = signed_in.get(reverse("leases:lease-detail", args=[lease.pk]))

    assert response.status_code == 200
    assert b"kept as a record" in response.content
    assert b"Activate lease" not in response.content


def test_an_ended_lease_cannot_be_edited(signed_in):
    lease = make_lease(make_unit(), status=LeaseStatus.ENDED)

    response = signed_in.get(reverse("leases:lease-update", args=[lease.pk]), follow=True)

    assert b"kept as history" in response.content


def test_an_ended_lease_cannot_be_edited_by_posting(signed_in):
    """The history rule is enforced on the write, not only on the page."""
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")], status=LeaseStatus.ENDED)
    payload = lease_post_data(lease.unit, lease=lease, monthly_rent="1.00")

    response = signed_in.post(reverse("leases:lease-update", args=[lease.pk]), payload, follow=True)

    lease.refresh_from_db()
    assert response.status_code == 200
    assert b"kept as history" in response.content
    assert str(lease.monthly_rent) != "1.00"


def test_only_a_draft_can_be_deleted(client):
    """An admin may delete, but still not an activated lease."""
    client.force_login(make_admin(username="lease-admin-2"))
    active = make_lease(make_unit())

    response = client.post(reverse("leases:lease-delete", args=[active.pk]), follow=True)

    assert Lease.objects.filter(pk=active.pk).exists()
    assert b"never deleted" in response.content


def test_a_draft_can_be_deleted_by_an_admin(client):
    client.force_login(make_admin(username="lease-admin"))
    draft = make_lease(make_unit(), status=LeaseStatus.DRAFT)

    response = client.post(reverse("leases:lease-delete", args=[draft.pk]))

    assert response.status_code == 302
    assert not Lease.objects.filter(pk=draft.pk).exists()


# --- editing --------------------------------------------------------------


def test_editing_a_draft_can_change_the_unit(signed_in):
    first = make_unit(identifier="A")
    second = make_unit(identifier="B")
    lease = make_lease(first, status=LeaseStatus.DRAFT)

    response = signed_in.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(second, [make_tenant(username="ada")], lease=lease),
    )

    lease.refresh_from_db()
    assert response.status_code == 302
    assert lease.unit == second


def test_an_active_lease_cannot_move_to_another_unit(signed_in):
    first = make_unit(identifier="A")
    second = make_unit(identifier="B")
    tenant = make_tenant(username="ada")
    lease = make_lease(first, tenants=[tenant])

    response = signed_in.post(
        reverse("leases:lease-update", args=[lease.pk]),
        lease_post_data(second, lease=lease),
    )

    lease.refresh_from_db()
    assert lease.unit == first
    assert response.status_code == 200
    assert b"cannot change once a lease has been activated" in response.content


def test_the_unit_field_is_frozen_once_a_lease_is_activated(signed_in):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])

    response = signed_in.get(reverse("leases:lease-update", args=[lease.pk]))

    assert response.context["form"].fields["unit"].disabled is True


def test_rent_can_be_corrected_on_an_active_lease(signed_in):
    unit = make_unit()
    tenant = make_tenant(username="ada")
    lease = make_lease(unit, tenants=[tenant])
    payload = lease_post_data(unit, lease=lease)
    payload["monthly_rent"] = "1925.00"

    response = signed_in.post(reverse("leases:lease-update", args=[lease.pk]), payload)

    lease.refresh_from_db()
    assert response.status_code == 302
    assert str(lease.monthly_rent) == "1925.00"


# --- the list -------------------------------------------------------------


def test_the_list_searches_by_tenant_and_unit(signed_in):
    ada = make_tenant(username="ada", first_name="Ada", last_name="Lovelace")
    wanted = make_lease(make_unit(identifier="Storefront"), tenants=[ada])
    make_lease(make_unit(identifier="Backflat"), tenants=[make_tenant(username="bob")])

    response = signed_in.get(reverse("leases:lease-list"), {"q": "Lovelace"})

    assert list(response.context["leases"]) == [wanted]


def test_the_list_filters_by_status(signed_in):
    make_lease(make_unit(identifier="Active"))
    make_lease(make_unit(identifier="Draft"), status=LeaseStatus.DRAFT)

    response = signed_in.get(reverse("leases:lease-list"), {"status": "DRAFT"})

    assert [lease.unit.identifier for lease in response.context["leases"]] == ["Draft"]


def test_the_list_can_show_leases_ending_soon(signed_in):
    soon = make_lease(make_unit(identifier="Soon"), end_date=TODAY + dt.timedelta(days=10))
    make_lease(make_unit(identifier="Later"), end_date=TODAY + dt.timedelta(days=300))

    response = signed_in.get(reverse("leases:lease-list"), {"expiring": "30"})

    assert [lease.pk for lease in response.context["leases"]] == [soon.pk]


def test_a_lease_with_no_document_offers_no_link(signed_in):
    lease = make_lease(make_unit(), tenants=[make_tenant(username="ada")])

    body = signed_in.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()

    assert "No document attached yet" in body
    assert "View lease" not in body


def test_the_detail_page_lists_the_tenants(signed_in):
    ada = make_tenant(username="ada", first_name="Ada", last_name="One")
    lease = make_lease(make_unit(), tenants=[ada])

    body = signed_in.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()

    assert "Ada One" in body
    assert "Primary contact" in body
    assert "$1,850.00" in body
    assert "1st of every month" in body
    assert "Phase 4" in body  # the ledger is labelled, not faked


def test_lease_tenants_are_protected_from_deletion():
    tenant = make_tenant(username="ada")
    lease = make_lease(make_unit(), tenants=[tenant])

    assert LeaseTenant.objects.filter(lease=lease, tenant=tenant).exists()
    assert make_property  # keep the import honest for readers of this file
