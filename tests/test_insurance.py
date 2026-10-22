"""E17: proof-of-insurance intake and manager decision; no automated screening."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.insurance.models import InsuranceProof, TenantState
from apps.insurance.services import state_for
from tests.factories import make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def world(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    manager = make_manager(username="ins-manager")
    tenant = make_tenant(username="ins-tenant")
    other = make_tenant(username="ins-other")
    lease = make_lease(tenants=[tenant], renters_insurance_required=True)
    other_lease = make_lease(tenants=[other], renters_insurance_required=True)
    return manager, tenant, other, lease, other_lease


def upload(tenant, lease, *, name="policy.pdf"):
    from apps.insurance import services

    return services.submit_proof(
        lease=lease,
        actor=tenant,
        file=SimpleUploadedFile(name, b"%PDF-1.4 synthetic", content_type="application/pdf"),
        policy_start=date(2026, 1, 1),
        policy_end=date(2027, 1, 1),
    )


def test_missing_then_submitted_then_accepted_three_state_flow(client, world):
    manager, tenant, _, lease, _ = world
    assert state_for(lease) == TenantState.MISSING

    client.force_login(tenant)
    response = client.post(
        reverse("tenant_insurance:insurance"),
        {
            "file": SimpleUploadedFile(
                "policy.pdf", b"%PDF-1.4 synthetic", content_type="application/pdf"
            ),
            "policy_start": "2026-01-01",
            "policy_end": "2027-01-01",
        },
    )
    assert response.status_code == 302
    proof = InsuranceProof.objects.get()
    assert proof.status == "SUBMITTED"
    assert state_for(lease) == TenantState.SUBMITTED
    tenant_page = client.get(reverse("tenant_insurance:insurance"))
    assert b"waiting for the manager" in tenant_page.content

    client.force_login(manager)
    assert client.get(reverse("insurance:staff-list")).status_code == 200
    detail = client.get(reverse("insurance:staff-detail", args=[lease.pk]))
    assert b"pending manager review" in detail.content
    response = client.post(
        reverse("insurance:staff-detail", args=[lease.pk]),
        {"decision": "ACCEPTED", "note": "Coverage and dates checked."},
    )
    assert response.status_code == 302
    proof.refresh_from_db()
    assert proof.status == "ACCEPTED"
    assert proof.reviewed_by == manager
    assert state_for(lease) == TenantState.ACCEPTED
    client.force_login(tenant)
    tenant_page = client.get(reverse("tenant_insurance:insurance"))
    assert b"Accepted by the manager" in tenant_page.content


def test_rejection_requires_a_reason_and_tenant_sees_it(client, world):
    manager, tenant, _, lease, _ = world
    proof = upload(tenant, lease)
    client.force_login(manager)
    response = client.post(
        reverse("insurance:staff-detail", args=[lease.pk]),
        {"decision": "REJECTED", "note": ""},
    )
    assert response.status_code == 200
    proof.refresh_from_db()
    assert proof.status == "SUBMITTED"

    response = client.post(
        reverse("insurance:staff-detail", args=[lease.pk]),
        {"decision": "REJECTED", "note": "The policy does not name the property."},
    )
    assert response.status_code == 302
    proof.refresh_from_db()
    assert proof.status == "REJECTED"
    client.force_login(tenant)
    page = client.get(reverse("tenant_insurance:insurance"))
    assert b"The policy does not name the property." in page.content


def test_replacement_is_append_only_and_visible_in_timeline(client, world):
    manager, tenant, _, lease, _ = world
    first = upload(tenant, lease)
    client.force_login(manager)
    client.post(
        reverse("insurance:staff-detail", args=[lease.pk]),
        {"decision": "REJECTED", "note": "Wrong address."},
    )
    second = upload(tenant, lease, name="replacement.pdf")
    assert InsuranceProof.objects.filter(lease=lease).count() == 2
    assert second.replaces_id == first.pk
    assert state_for(lease) == TenantState.SUBMITTED

    timeline = client.get(reverse("timeline:lease", args=[lease.pk]))
    assert b"Renters insurance proof submitted" in timeline.content
    assert b"Renters insurance proof rejected" in timeline.content


def test_tenant_cannot_read_another_tenants_proof_or_staff_screen(client, world):
    _, tenant, other, lease, other_lease = world
    proof = upload(tenant, lease)
    client.force_login(other)
    assert (
        client.get(reverse("tenant_insurance:proof-document", args=[proof.pk])).status_code == 404
    )
    assert client.get(reverse("insurance:staff-list")).status_code == 403
    assert client.get(reverse("insurance:staff-detail", args=[lease.pk])).status_code == 403


def test_requirement_off_shows_no_warning_or_upload_requirement(client):
    tenant = make_tenant(username="ins-not-required")
    lease = make_lease(tenants=[tenant], renters_insurance_required=False)
    client.force_login(tenant)
    response = client.get(reverse("tenant_insurance:insurance"))
    assert response.status_code == 200
    assert b"does not require" in response.content
    assert state_for(lease) == TenantState.NOT_REQUIRED
