"""Disposable Phase 9 browser review. No development records or normal cookies."""

import os
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.ledger import services
from apps.ledger.models import Direction
from apps.maintenance import services as maintenance
from tests.factories import (
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_property,
    make_tenant,
    make_unit,
)


class QAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        response = self.get_response(request)
        if os.environ.get("RHP_DASHBOARD_QA") == "noscript":
            response["Content-Security-Policy"] = "script-src 'none'"
        connection.close()
        return response


@pytest.mark.skipif(not os.environ.get("RHP_DASHBOARD_QA"), reason="Opt-in dashboard browser QA")
@pytest.mark.django_db(transaction=True)
def test_disposable_dashboard(live_server, settings):
    settings.SESSION_COOKIE_NAME = "rhp_dashboard_qa_session"
    settings.CSRF_COOKIE_NAME = "rhp_dashboard_qa_csrf"
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    settings.MIDDLEWARE = ["tests.test_dashboard_browser.QAMiddleware", *settings.MIDDLEWARE]
    live_server.thread.httpd.get_app().application.application.load_middleware()
    manager = make_manager(username="dashboard-manager")
    tenant = make_tenant(username="dashboard-tenant", first_name="Alex", last_name="Example")
    prop = make_property(name="Alder Court", street="100 Example Avenue")
    unit = make_unit(prop, identifier="Studio A")
    make_unit(prop, identifier="Studio B")
    today = timezone.localdate()
    lease = make_lease(
        unit,
        tenants=[tenant],
        start_date=today - timedelta(days=40),
        end_date=today + timedelta(days=25),
    )
    charge = make_charge(lease, amount=Decimal("1850"), due_date=today.replace(day=1))
    services.create_adjustment(
        charge,
        amount=Decimal("100"),
        direction=Direction.DECREASE,
        reason="Synthetic correction",
        actor=manager,
    )
    make_payment(lease, amount=Decimal("500"))
    ticket = maintenance.create_request(
        actor=manager,
        property=prop,
        unit=unit,
        title="Kitchen faucet drip",
        category="plumbing",
        description="Synthetic browser review",
    )
    record(
        manager, AuditAction.MAINTENANCE_CHANGED, obj=ticket, summary="Private note not displayed"
    )
    input(
        f"\nPhase 9 QA: {live_server.url}/account/login/\n"
        "dashboard-manager / unit-test-password-41\nEnter to tear down disposable records.\n"
    )
    assert lease.unit_id == unit.pk
