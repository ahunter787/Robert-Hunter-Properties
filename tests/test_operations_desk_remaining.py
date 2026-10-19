"""Remaining E11 workspaces: scoped navigation, not new business authority."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.documents.models import Document
from apps.maintenance import services
from apps.maintenance.models import Update
from tests.factories import (
    make_cycle,
    make_lease,
    make_maintenance,
    make_manager,
    make_property,
    make_responsibility,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


def test_person_workspace_separates_current_history_and_access(client):
    manager = make_manager()
    tenant = make_tenant()
    current = make_lease(tenants=[tenant])
    old = make_lease(
        make_unit(),
        tenants=[tenant],
        status="ENDED",
        start_date=dt.date(2020, 1, 1),
        end_date=dt.date(2020, 12, 31),
        ended_on=dt.date(2020, 12, 31),
        end_reason="END_OF_TERM",
    )
    client.force_login(manager)
    url = reverse("manage:account-detail", args=[tenant.pk])
    page = client.get(url)
    assert page.context["current_tenancies"] == [current]
    assert page.context["other_tenancies"] == [old]
    assert b"Back to tenant accounts" not in page.content
    assert b"Deactivate account" not in page.content
    assert b"Deactivate account" in client.get(url, {"section": "access"}).content
    assert b"Add photo" in client.get(url, {"section": "contact"}).content
    client.force_login(tenant)
    assert client.get(url, {"section": "access"}).status_code == 403


@pytest.fixture
def conversations():
    manager = make_manager()
    first, second = make_tenant(username="first"), make_tenant(username="second")
    a = make_lease(tenants=[first])
    b = make_lease(make_unit(a.unit.property, identifier="Other"), tenants=[second])
    ticket = services.create_request(
        actor=manager,
        property=a.unit.property,
        title="Shared work",
        description="Private original description",
        category="general",
    )
    services.share_request(ticket, actor=manager, lease=a, introduction="First introduction")
    services.share_request(ticket, actor=manager, lease=b, introduction="Second introduction")
    services.add_update(ticket, actor=manager, lease_id=a.pk, body="First private reply")
    services.add_update(ticket, actor=manager, lease_id=b.pk, body="Second private reply")
    services.add_update(ticket, actor=manager, body="Internal private note")
    return manager, first, second, a, b, ticket


def test_selected_conversations_and_internal_notes_do_not_mix(client, conversations):
    manager, first, _, a, b, ticket = conversations
    aa, bb = ticket.audiences.get(lease=a), ticket.audiences.get(lease=b)
    url = reverse("maintenance:detail", args=[ticket.public_id])
    client.force_login(manager)
    before = Update.objects.count()
    page = client.get(url, {"audience": aa.pk})
    assert b"First private reply" in page.content
    assert b"Second private reply" not in page.content
    assert b"Internal private note" not in page.content
    page = client.get(url, {"section": "internal"})
    assert b"Internal private note" in page.content
    assert b"First private reply" not in page.content
    assert Update.objects.count() == before
    client.force_login(first)
    tenant_url = reverse("tenant_maintenance:detail", args=[ticket.public_id])
    assert client.get(tenant_url, {"audience": bb.pk}).status_code == 404
    for section in ("internal", "costs", "history"):
        assert client.get(tenant_url, {"section": section}).status_code == 403
    assert (
        b"Private original description" not in client.get(tenant_url, {"section": "work"}).content
    )


def test_form_selects_the_visible_conversation(client, conversations):
    manager, _, _, a, _, ticket = conversations
    client.force_login(manager)
    audience = ticket.audiences.get(lease=a)
    page = client.get(
        reverse("maintenance:action", args=[ticket.public_id, "update"]), {"audience": audience.pk}
    )
    assert page.context["form"]["audience"].value() == audience.pk
    assert (
        client.get(
            reverse("maintenance:detail", args=[ticket.public_id]), {"audience": "bogus"}
        ).status_code
        == 404
    )


def test_selected_former_tenancy_cannot_borrow_current_tenancys_write_access(client):
    manager, tenant = make_manager(), make_tenant()
    old = make_lease(tenants=[tenant])
    current = make_lease(make_unit(old.unit.property, identifier="Current"), tenants=[tenant])
    ticket = services.create_request(
        actor=manager,
        property=old.unit.property,
        title="Shared repair",
        description="Private",
        category="general",
    )
    for lease in (old, current):
        services.share_request(ticket, actor=manager, lease=lease, introduction="Notice")
    old.status, old.ended_on, old.end_reason = "ENDED", timezone.localdate(), "MUTUAL"
    old.save()
    client.force_login(tenant)
    url = reverse("tenant_maintenance:detail", args=[ticket.public_id])
    assert (
        client.get(url, {"audience": ticket.audiences.get(lease=old).pk}).context["can_write"]
        is False
    )
    assert (
        client.get(url, {"audience": ticket.audiences.get(lease=current).pk}).context["can_write"]
        is True
    )


def test_worker_sections_preserve_assignment_and_financial_boundaries(client, conversations):
    manager, _, _, _, _, ticket = conversations
    worker = make_maintenance()
    url = reverse("maintenance:detail", args=[ticket.public_id])
    client.force_login(worker)
    assert client.get(url).status_code == 404
    services.change_work(
        ticket, actor=manager, status="ACKNOWLEDGED", priority=2, assigned_to=worker
    )
    assert client.get(url).status_code == 200
    for section in ("costs", "history"):
        assert client.get(url, {"section": section}).status_code == 403
    assert b"/photo/" not in client.get(url).content


def test_documents_include_lease_context_but_reject_mismatched_units(client):
    client.force_login(make_manager())
    lease = make_lease()
    other = make_property()
    Document.objects.create(title="Lease evidence", lease=lease, file="synthetic.pdf")
    url = reverse("documents:list")
    assert b"Lease evidence" in client.get(url, {"property": lease.unit.property_id}).content
    assert b"Lease evidence" not in client.get(url, {"property": other.pk}).content
    assert client.get(url, {"property": other.pk, "unit": lease.unit_id}).status_code == 404
    assert client.get(url, {"property": "invalid"}).status_code == 404


def test_recovery_workspace_and_cycle_context_are_property_scoped(client):
    client.force_login(make_manager())
    property_obj = make_property(name="Recovery property")
    other = make_property(name="Other property")
    bill = make_cycle(make_responsibility(property_obj, label="Electricity"))
    url = reverse("responsibilities:overview")
    assert b"Electricity" in client.get(url, {"property": property_obj.pk}).content
    assert b"Electricity" not in client.get(url, {"property": other.pk}).content
    assert client.get(url, {"property": property_obj.pk, "unit": "bogus"}).status_code == 404
    allocation = reverse("responsibilities:cycle-shares", args=[bill.pk])
    assert client.get(allocation, {"property": other.pk}).status_code == 404
    page = client.get(allocation, {"workspace": "recoveries"})
    assert page.context["back_url"] == url + f"?property={property_obj.pk}"
    assert (
        "evil.example"
        not in client.get(allocation, {"return": "https://evil.example"}).content.decode()
    )
