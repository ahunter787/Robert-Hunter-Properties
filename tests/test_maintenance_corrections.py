"""Owner review: dependent location selection and explicit entry authorization."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.maintenance import forms, services
from apps.maintenance.models import MaintenanceRequest, Update
from tests.factories import make_lease, make_manager, make_tenant, make_unit

pytestmark = pytest.mark.django_db


def test_location_only_get_scopes_units_and_never_writes(client):
    manager = make_manager()
    first = make_unit(identifier="Unit Alpha")
    second = make_unit(identifier="Unit Beta")
    client.force_login(manager)
    url = reverse("maintenance:create")
    response = client.get(url)
    assert list(response.context["form"].fields["unit"].queryset) == []
    response = client.get(url, {"property": first.property_id, "load_units": 1, "unit": second.pk})
    assert list(response.context["form"].fields["unit"].queryset) == [first]
    assert response.context["form"]["unit"].value() is None
    response = client.get(url, {"property": first.property_id, "unit": first.pk, "continue": 1})
    assert "Submit request" in response.content.decode()
    assert response.context["form"]["unit"].value() == first.pk
    assert MaintenanceRequest.objects.count() == 0
    response = client.get(reverse("maintenance:units"), {"property": second.property_id})
    assert "Unit Beta" in response.content.decode()
    assert "Unit Alpha" not in response.content.decode()
    assert "selected" not in response.content.decode()
    assert "hx-sync" in str(forms.LocationForm()["property"])


def test_staff_submission_rejects_forged_unit_preserves_details(client):
    manager = make_manager()
    unit, other = make_unit(), make_unit()
    client.force_login(manager)
    data = {
        "property": unit.property_id,
        "unit": other.pk,
        "title": "Loose hinge",
        "description": "Keep this description",
        "category": "general",
    }
    response = client.post(reverse("maintenance:create"), data)
    assert response.status_code == 200
    assert "unit" in response.context["form"].errors
    assert response.context["form"]["description"].value() == data["description"]
    assert not MaintenanceRequest.objects.exists()
    with pytest.raises(ValidationError):
        services.create_request(
            actor=manager,
            property=unit.property,
            unit=other,
            title="Mismatch",
            description="No",
            category="general",
        )
    data["unit"] = ""
    response = client.post(reverse("maintenance:create"), data)
    assert response.status_code == 302
    assert MaintenanceRequest.objects.get().unit_id is None


def test_empty_property_and_unit_endpoint_authorization(client):
    from tests.factories import make_property

    prop = make_property()
    manager = make_manager()
    client.force_login(manager)
    form = forms.LocationForm({"property": prop.pk, "unit": ""})
    assert form.is_valid()
    assert not form.fields["unit"].queryset.exists()
    response = client.get(reverse("maintenance:units"), {"property": "invalid"})
    assert response.status_code == 200
    assert response.content.decode().count("<option") == 1
    client.force_login(make_tenant())
    assert client.get(reverse("maintenance:units"), {"property": prop.pk}).status_code == 403


def permission_world():
    manager, tenant = make_manager(), make_tenant()
    lease = make_lease(tenants=[tenant])
    ticket = services.create_request(
        actor=tenant,
        property=lease.unit.property,
        unit=lease.unit,
        lease=lease,
        title="Door repair",
        description="Hinge",
        category="general",
    )
    return manager, tenant, lease, ticket


def test_permission_checkbox_saved_state_and_unchecked_withdrawal(client):
    manager, tenant, lease, ticket = permission_world()
    services.set_entry_permission(ticket, actor=tenant, lease_id=lease.pk, permission=True)
    audience = ticket.audiences.get()
    client.force_login(tenant)
    url = reverse("tenant_maintenance:action", args=[ticket.public_id, "permission"])
    response = client.get(url)
    assert response.context["form"]["permission"].value() is True
    assert 'type="checkbox"' in response.content.decode()
    assert "assigned repair professionals" in response.content.decode()
    assert "source_note" not in response.context["form"].fields
    assert client.post(url, {"audience": audience.pk}).status_code == 302
    audience.refresh_from_db()
    assert audience.permission_to_enter is False
    assert audience.permission_by == tenant
    client.force_login(manager)
    staff_url = reverse("maintenance:action", args=[ticket.public_id, "permission"])
    response = client.post(staff_url, {"audience": audience.pk, "permission": "on"})
    assert "source_note" in response.context["form"].errors
    audience.refresh_from_db()
    assert audience.permission_to_enter is False


def test_staff_source_note_is_private_and_service_enforced(client):
    manager, tenant, lease, ticket = permission_world()
    with pytest.raises(ValidationError):
        services.set_entry_permission(ticket, actor=manager, lease_id=lease.pk, permission=True)
    note = "Private source: tenant telephone confirmation today"
    services.set_entry_permission(
        ticket,
        actor=manager,
        lease_id=lease.pk,
        permission=True,
        source_note=note,
    )
    assert not Update.objects.filter(request=ticket, body__contains=note).exists()
    event = AuditEvent.objects.filter(
        object_id=ticket.pk, summary="Tenant entry authorization updated."
    ).get()
    assert event.metadata["source_note"] == note
    client.force_login(tenant)
    response = client.get(reverse("tenant_maintenance:detail", args=[ticket.public_id]))
    assert note not in response.content.decode()
    assert "Tenant-authorized entry: " in response.content.decode()
    assert "Recorded by" in response.content.decode()


def test_permission_audience_switch_uses_scoped_saved_value(client):
    manager, tenant, lease, ticket = permission_world()
    # A property-level request can have different authorization for each tenancy.
    shared = services.create_request(
        actor=manager,
        property=lease.unit.property,
        title="Roof",
        description="Private",
        category="structural",
    )
    other = make_tenant(username="other")
    other_lease = make_lease(make_unit(lease.unit.property, identifier="2"), tenants=[other])
    for target in (lease, other_lease):
        services.share_request(shared, actor=manager, lease=target, introduction="Roof update")
    services.set_entry_permission(shared, actor=tenant, lease_id=lease.pk, permission=True)
    client.force_login(manager)
    url = reverse("maintenance:action", args=[shared.public_id, "permission"])
    for target, expected in ((lease, True), (other_lease, False)):
        audience = shared.audiences.get(lease=target)
        response = client.get(url, {"audience": audience.pk})
        assert response.context["form"]["permission"].value() is expected
    client.force_login(tenant)
    url = reverse("tenant_maintenance:action", args=[shared.public_id, "permission"])
    foreign = shared.audiences.get(lease=other_lease)
    response = client.post(url, {"audience": foreign.pk, "permission": "on"})
    assert "audience" in response.context["form"].errors
    with pytest.raises(PermissionDenied):
        services.set_entry_permission(
            shared, actor=tenant, lease_id=other_lease.pk, permission=True
        )
