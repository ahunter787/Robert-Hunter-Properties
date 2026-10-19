"""Opt-in disposable E11 browser fixture; never creates development-portfolio data."""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.documents.models import Document
from apps.maintenance import services
from tests.factories import (
    make_cycle,
    make_lease,
    make_manager,
    make_property,
    make_responsibility,
    make_share,
    make_tenant,
    make_unit,
)


class QAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        response = self.get_response(request)
        if os.environ.get("RHP_DESIGN_QA") == "noscript":
            response["Content-Security-Policy"] = "script-src 'none'"
        connection.close()
        return response


@pytest.mark.skipif(not os.environ.get("RHP_DESIGN_QA"), reason="Opt-in Operations Desk browser QA")
@pytest.mark.django_db(transaction=True)
def test_disposable_operations_desk(live_server, settings):
    # Cookies are host-scoped, not port-scoped. Never replace the owner's localhost login.
    settings.SESSION_COOKIE_NAME = "rhp_design_qa_session"
    settings.CSRF_COOKIE_NAME = "rhp_design_qa_csrf"
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    settings.MIDDLEWARE = ["tests.test_operations_desk_browser.QAMiddleware", *settings.MIDDLEWARE]
    live_server.thread.httpd.get_app().application.application.load_middleware()
    manager = make_manager(username="design-manager")
    probe = Client()
    probe.force_login(manager)
    assert "rhp_design_qa_session" in probe.cookies
    assert probe.get("/manage/").status_code == 200
    tenant = make_tenant(username="design-tenant", first_name="Alex", last_name="Example")
    # Synthetic images stay in test storage and never become application defaults.
    samples = Path(__file__).resolve().parents[1] / "tools/design_prototype/static"

    def sample(name):
        return SimpleUploadedFile(name, (samples / name).read_bytes(), content_type="image/png")

    a = make_property(
        name="Alder Court", street="100 Example Avenue", banner_image=sample("alder.png")
    )
    b = make_property(
        name="Cedar House", street="200 Example Avenue", banner_image=sample("cedar.png")
    )
    u = make_unit(a, identifier="Studio A", square_feet=750, photo=sample("studio.png"))
    studio_b = make_unit(a, identifier="Studio B", square_feet=600)
    make_unit(b, identifier="Apartment 1", square_feet=900)
    lease = make_lease(u, tenants=[tenant])
    tenant.tenant_profile.photo = sample("portrait.png")
    tenant.tenant_profile.save()
    make_tenant(username="without-portrait", first_name="Zoe", last_name="Example")
    bill = make_cycle(
        make_responsibility(a, label="Electricity"), total_amount=Decimal("237.00"), months=3
    )
    make_share(bill, u, monthly_amount=Decimal("33.20"))
    make_share(bill, studio_b, monthly_amount=Decimal("45.80"))
    ticket = services.create_request(
        actor=manager,
        property=a,
        unit=u,
        title="Kitchen faucet drip",
        category="plumbing",
        description="Synthetic browser review only",
    )
    services.share_request(
        ticket, actor=manager, lease=lease, introduction="We are arranging a faucet repair."
    )
    services.add_update(ticket, actor=manager, body="Synthetic internal scheduling note.")
    services.add_update(
        ticket, actor=manager, lease_id=lease.pk, body="Please let us know when you are available."
    )
    Document.objects.create(title="Studio A example notice", lease=lease, file="example.pdf")
    input(
        f"\nE11 browser QA ready at {live_server.url}/account/login/\n"
        "Accounts design-manager / design-tenant; password unit-test-password-41\n"
        f"Unit /manage/units/{u.pk}/; Property /manage/properties/{a.pk}/\n"
        f"Lease /manage/leases/{lease.pk}/; "
        f"Allocation /manage/responsibilities/cycles/{bill.pk}/shares/\n"
        f"Maintenance /manage/maintenance/{ticket.public_id}/; "
        f"Tenant /manage/accounts/{tenant.pk}/\n"
        "Press Enter after browser review to tear down all disposable records.\n"
    )
    assert lease.unit_id == u.pk
