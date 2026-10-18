"""Opt-in manual browser harness, isolated from RHP's development data.

RHP_BROWSER_QA=1 uv run pytest tests/test_maintenance_browser.py -s
    --liveserver=localhost:8011

Keep the PTY open while using the browser. Enter finishes QA and destroys the test
database through pytest-django's normal teardown. Never run another DB suite concurrently.
"""

import os

import pytest

from apps.maintenance.models import MaintenanceRequest, Recharge
from tests.factories import make_lease, make_maintenance, make_manager, make_tenant


class NoScriptQAMiddleware:
    """Test-only script blocking and connection cleanup for live-server teardown."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        response = self.get_response(request)
        if os.environ.get("RHP_BROWSER_QA") != "corrections":
            response["Content-Security-Policy"] = "script-src 'none'"
        connection.close()
        return response


@pytest.fixture(autouse=True)
def browser_settings(settings):
    settings.MIDDLEWARE = [
        "tests.test_maintenance_browser.NoScriptQAMiddleware",
        *settings.MIDDLEWARE,
    ]


@pytest.mark.skipif(
    os.environ.get("RHP_BROWSER_QA")
    not in ("1", "noscript", "corrections", "corrections-noscript"),
    reason="Opt-in interactive browser QA",
)
@pytest.mark.django_db(transaction=True)
def test_disposable_browser_workflow(live_server, settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # The session-scoped live server loaded its handler before function-scoped settings.
    live_server.thread.httpd.get_app().application.application.load_middleware()
    manager = make_manager(username="qa-manager")
    make_maintenance(username="qa-worker")
    tenant = make_tenant(username="qa-tenant", email="qa-tenant@example.test")
    lease = make_lease(tenants=[tenant])
    if os.environ.get("RHP_BROWSER_QA", "").startswith("corrections"):
        from apps.maintenance import services
        from tests.factories import make_unit

        other = make_unit(identifier="QA Other Unit")
        other.property.name = "QA Second Property"
        other.property.save()
        lease.unit.property.name = "QA First Property"
        lease.unit.property.save()
        lease.unit.identifier = "QA First Unit"
        lease.unit.save()
        request = services.create_request(
            actor=tenant,
            property=lease.unit.property,
            unit=lease.unit,
            lease=lease,
            title="QA entry permission",
            description="Synthetic browser evidence",
            category="general",
            permission=True,
        )
        input(
            f"\nCorrections QA ready: {live_server.url}/account/login/\n"
            "Accounts qa-manager / qa-tenant; password unit-test-password-41\n"
            f"Permission request: /manage/maintenance/{request.public_id}/permission/\n"
            "Create QA location check; record manager permission with a private source note.\n"
            "Press Enter when browser QA is complete.\n"
        )
        assert MaintenanceRequest.objects.filter(title="QA location check", unit=other).exists()
        assert request.audiences.get().permission_by == manager
        return
    if os.environ.get("RHP_BROWSER_QA") == "noscript":
        from django.utils import timezone

        from apps.maintenance import services

        request = services.create_request(
            actor=tenant,
            property=lease.unit.property,
            unit=lease.unit,
            lease=lease,
            title="QA kitchen leak",
            description="Disposable QA follow-up",
            category="plumbing",
        )
        services.change_work(request, actor=manager, status="CLOSED", priority=2)
        services.record_cost(
            request,
            actor=manager,
            amount="237.00",
            description="QA plumber invoice",
            incurred_on=timezone.localdate(),
        )
    input(
        f"\nIsolated QA ready: {live_server.url}/account/login/\n"
        "Accounts: qa-manager / qa-worker / qa-tenant\n"
        "Test password: unit-test-password-41\n"
        "Complete submission, assignment, completion, closure, follow-up, and reviewed recharge.\n"
        "Press Enter only when browser QA is finished.\n"
    )
    request = MaintenanceRequest.objects.get(title="QA kitchen leak")
    assert request.audiences.filter(unresolved=True).exists()
    assert Recharge.objects.filter(cost__request=request).count() == 1
