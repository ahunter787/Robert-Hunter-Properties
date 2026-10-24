"""E18 shell and action-first dashboard projections."""

import pytest
from django.urls import reverse

from tests.factories import make_lease, make_manager, make_property, make_tenant, make_unit
from tests.test_communications import start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


def test_manager_navigation_is_grouped_by_job(client):
    manager = make_manager(username="e18-nav-manager")
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    groups = response.context["portal_groups"]
    assert [group["title"] for group in groups] == [
        "",
        "Portfolio",
        "People",
        "Leasing",
        "Money",
        "Work",
        "Communications",
        "Workspace",
    ]
    labels = [item["label"] for item in response.context["portal_nav"]]
    assert labels[-3:] == ["Messages", "Announcements", "Documents"]


def test_messages_badge_uses_authorized_unread_count(client):
    manager = make_manager(username="e18-badge-manager")
    tenant = make_tenant(username="e18-badge-tenant", first_name="Alex", last_name="Example")
    lease = make_lease(tenants=[tenant])
    start(tenant, lease, tenant=tenant, body="A new question")
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    message_item = next(
        item for item in response.context["portal_nav"] if item["key"] == "communications"
    )
    assert message_item["badge"] == 1
    assert response.context["portal_unread"] == 1
    assert b"portal-nav-badge" in response.content


def test_tenant_portal_has_a_compact_mobile_nav_and_next_steps(client):
    tenant = make_tenant(username="e18-tenant-nav", first_name="Alex", last_name="Example")
    make_lease(tenants=[tenant], renters_insurance_required=True)
    client.force_login(tenant)
    response = client.get(reverse("accounts:home"))
    assert response.status_code == 200
    assert b"portal-bottom-nav" in response.content
    labels = [step["label"] for step in response.context["next_steps"]]
    assert "Supply renters insurance proof" in labels
    assert b"Your next steps" in response.content


def test_manager_dashboard_surfaces_attention_then_the_metric_groups(client):
    manager = make_manager(username="e18-attention-manager")
    tenant = make_tenant(username="e18-attention-tenant", first_name="Alex", last_name="Example")
    make_lease(tenants=[tenant], renters_insurance_required=True)
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    labels = [item["label"] for item in response.context["dashboard"]["attention"]]
    assert "Renters insurance missing" in labels
    body = response.content.decode().split('id="main"', 1)[1]
    assert body.index("Needs attention today") < body.index("Rent &amp; Payments")


def test_manager_setup_checklist_guides_an_empty_install(client):
    manager = make_manager(username="e18-empty-manager")
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    assert response.context["setup_complete_count"] < 4
    assert b"Set up RHP" in response.content
    assert b"Add a property" in response.content


def test_manager_setup_checklist_completes_with_existing_records(client):
    manager = make_manager(username="e18-setup-manager")
    tenant = make_tenant(username="e18-setup-tenant")
    property = make_property(name="E18 Setup Court")
    unit = make_unit(property, identifier="Setup 1")
    make_lease(unit, tenants=[tenant])
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    assert response.context["setup_complete_count"] == 4
    assert b"Set up RHP" not in response.content


def test_sidebar_account_is_one_profile_link_with_avatar(client):
    manager = make_manager(username="e18-sidebar-manager")
    client.force_login(manager)
    response = client.get(reverse("manage:home"))
    assert response.status_code == 200
    assert b'class="portal-account"' in response.content
    assert reverse("accounts:profile").encode() in response.content
    assert b"Profile &amp; account" not in response.content
    assert b'aria-label="No photo"' in response.content
