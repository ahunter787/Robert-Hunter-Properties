"""Opt-in synthetic financial checkpoint; isolated database, cookies and mail."""

import os
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import ChargeKind, Direction, PaymentStatus
from tests.factories import (
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_property,
    make_responsibility,
    make_tenant,
    make_unit,
)


class QAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        response = self.get_response(request)
        if (
            os.environ.get("RHP_FINANCIAL_QA") == "noscript"
            or request.GET.get("qa_scripts") == "off"
        ):
            response["Content-Security-Policy"] = "script-src 'none'"
        connection.close()
        return response


@pytest.mark.skipif(not os.environ.get("RHP_FINANCIAL_QA"), reason="Opt-in financial browser QA")
@pytest.mark.django_db(transaction=True)
def test_disposable_financial_workspace(live_server, settings):
    settings.SESSION_COOKIE_NAME = "rhp_financial_qa_session"
    settings.CSRF_COOKIE_NAME = "rhp_financial_qa_csrf"
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    settings.MIDDLEWARE = [
        "tests.test_financial_clarity_browser.QAMiddleware",
        *settings.MIDDLEWARE,
    ]
    live_server.thread.httpd.get_app().application.application.load_middleware()
    manager = make_manager(username="financial-manager")
    prop = make_property(name="Alder Court", street="100 Example Avenue")
    today = timezone.localdate()
    paths = []
    for name in ("Corrected", "Upcoming", "Credit", "Paid", "Empty", "Pending"):
        tenant = make_tenant(
            username=f"financial-{name.lower()}", first_name=name, last_name="Example"
        )
        lease = make_lease(
            make_unit(prop, identifier=f"Studio {name}"),
            tenants=[tenant],
            start_date=today - timedelta(days=800 if name == "Corrected" else 40),
            end_date=today + timedelta(days=400),
        )
        if name == "Credit":
            make_payment(lease, amount=Decimal("200"))
        elif name != "Empty":
            charge = make_charge(
                lease,
                amount=Decimal("840"),
                due_date=today + timedelta(days=15)
                if name == "Upcoming"
                else today - timedelta(days=1),
            )
            if name == "Corrected":
                make_charge(
                    lease,
                    amount=Decimal("200"),
                    due_date=today - timedelta(days=500),
                    description="Older rent charge",
                )
                electricity = make_responsibility(prop, label="Electricity")
                make_charge(
                    lease,
                    kind=ChargeKind.RESPONSIBILITY,
                    responsibility=electricity,
                    amount=Decimal("79"),
                    description="Electricity for October",
                )
                services.create_adjustment(
                    charge,
                    amount=Decimal("40"),
                    direction=Direction.DECREASE,
                    reason="Synthetic correction",
                    actor=manager,
                )
                make_payment(lease, amount=Decimal("500"))
            elif name == "Paid":
                make_payment(lease, amount=Decimal("840"))
            elif name == "Pending":
                make_payment(lease, amount=Decimal("75"), status=PaymentStatus.PENDING)
        paths.append(f"{name}: /manage/ledger/leases/{lease.pk}/")
    from tests.ledger.test_bill_presentation import example_bill

    bill_lease, _bill_tenant, bill_due = example_bill()
    make_payment(bill_lease, amount=Decimal("1000"), payment_date=bill_due)
    make_charge(
        bill_lease,
        amount=Decimal("25"),
        kind=ChargeKind.MANUAL,
        due_date=bill_due + timedelta(days=1),
        description="Separate-date one-time charge",
    )
    paths.append(f"Bill: /manage/ledger/leases/{bill_lease.pk}/")
    recovery = make_lease(
        make_unit(prop, identifier="History recovery"),
        start_date=today - timedelta(days=80),
        end_date=today + timedelta(days=365),
        billing_start_date=None,
    )
    make_charge(recovery, amount=Decimal("1000"), due_date=today - timedelta(days=20))
    make_payment(recovery, amount=Decimal("160"))
    paths.append(f"Recovery: /manage/leases/{recovery.pk}/onboarding/")
    input(
        f"\nFinancial QA: {live_server.url}/account/login/\n"
        "financial-manager / unit-test-password-41\n"
        + "\n".join(paths)
        + "\nTenant usernames: financial-credit, financial-pending, etc.; same test password.\n"
        "Enter to tear down disposable records.\n"
    )
