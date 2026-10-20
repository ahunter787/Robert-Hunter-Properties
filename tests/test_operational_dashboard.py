"""Phase 9: exact drill-downs, ledger arithmetic and safe operational audit reads."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import record
from apps.communications import services as communications
from apps.dashboard import activity, services
from apps.ledger import services as ledger
from apps.ledger.models import ChargeKind, Direction, PaymentStatus
from apps.maintenance.models import Audience, MaintenanceRequest, Status
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_maintenance,
    make_manager,
    make_payment,
    make_property,
    make_responsibility,
    make_superadmin,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


def test_all_metrics_have_exact_detail_destinations(client):
    manager = make_manager()
    make_charge(amount=Decimal("100"), due_date=timezone.localdate() - timedelta(days=1))
    client.force_login(manager)
    dashboard = client.get(reverse("manage:home"))
    assert dashboard.status_code == 200
    for metric in dashboard.context["dashboard"]["metrics"].values():
        response = client.get(metric.url)
        assert response.status_code == 200, metric.key
        assert response.context["metric"].value == metric.value
        assert response.context["page"].paginator.count == len(metric.rows)
    assert client.get(reverse("manage:dashboard-detail", args=["invented"])).status_code == 404


def test_corrected_charges_keep_original_month_and_credit_separate():
    manager = make_manager()
    today = timezone.localdate()
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100"), due_date=today.replace(day=1))
    ledger.create_adjustment(
        charge,
        amount=Decimal("20"),
        direction=Direction.DECREASE,
        reason="Correction",
        actor=manager,
    )
    make_charge(lease, amount=Decimal("25"), kind=ChargeKind.NNN)
    prior = today.replace(day=1) - timedelta(days=1)
    make_charge(lease, amount=Decimal("600"), due_date=prior)
    make_payment(lease, amount=Decimal("30"), payment_date=today)
    make_payment(lease, amount=Decimal("50"), status=PaymentStatus.PENDING)
    reversed_payment = make_payment(lease, amount=Decimal("80"))
    ledger.reverse_payment(reversed_payment, reason="Wrong payment", actor=manager)
    credit_lease = make_lease(make_unit())
    make_payment(credit_lease, amount=Decimal("200"), payment_date=prior)
    metrics = services.project(manager)["metrics"]
    assert metrics["month-charges"].value == Decimal("105")
    assert metrics["month-rent"].value == Decimal("80")
    assert metrics["month-payments"].value == Decimal("30")
    assert metrics["credits"].value == Decimal("200")
    assert metrics["balances"].value == Decimal("675")
    assert len(metrics["month-rent"].rows[0].corrections) == 1


def test_occupancy_and_cumulative_lease_windows():
    manager = make_manager()
    today = timezone.localdate()
    unit = make_unit()
    make_lease(unit, start_date=today - timedelta(days=2), end_date=today + timedelta(days=30))
    future = make_unit()
    make_lease(future, start_date=today + timedelta(days=1), end_date=today + timedelta(days=90))
    make_lease(make_unit(), status="DRAFT")
    metrics = services.project(manager)["metrics"]
    assert metrics["occupied"].value == 1
    assert metrics["vacant"].value == 2
    assert metrics["ending-30"].value == 1
    assert metrics["ending-90"].value == 2


@pytest.mark.parametrize("factory", [make_tenant, make_maintenance])
def test_direct_portfolio_endpoints_reject_other_roles(client, factory):
    user = factory()
    client.force_login(user)
    assert client.get(reverse("manage:activity")).status_code == 403
    assert (
        client.get(reverse("manage:dashboard-detail", args=["month-payments"])).status_code == 403
    )


def test_activity_redacts_raw_text_and_preserves_missing_targets(client):
    manager = make_manager()
    prop = make_property()
    lease = make_lease(make_unit(prop))
    record(
        manager,
        AuditAction.PAYMENT_RECORDED,
        lease=lease,
        summary="SECRET MESSAGE BODY",
        private="HIDDEN TOKEN",
    )
    record(manager, AuditAction.ROLE_CHANGED, obj=manager, summary="ROLE SECRET")
    AuditEvent.objects.create(
        action=AuditAction.CHARGE_CREATED,
        object_type="unknown.Removed",
        object_id=999999,
        summary="PRIVATE",
    )
    client.force_login(manager)
    response = client.get(reverse("manage:activity"))
    assert response.status_code == 200
    assert response.context["page"].paginator.count == 2
    assert all(
        word not in response.content.decode()
        for word in ("SECRET", "HIDDEN", "PRIVATE", "Role changed")
    )
    assert b"Historical record unavailable" in response.content
    assert (
        client.get(reverse("manage:activity"), {"property": prop.pk, "tenancy": lease.pk})
        .context["page"]
        .paginator.count
        == 1
    )
    assert client.get(reverse("manage:activity"), {"action": "ROLE_CHANGED"}).status_code == 400
    client.force_login(make_admin())
    assert client.get(reverse("manage:activity")).context["page"].paginator.count == 2
    client.force_login(make_superadmin())
    assert client.get(reverse("manage:activity")).context["page"].paginator.count == 3


def test_activity_pagination_and_invalid_filters(client):
    manager = make_manager()
    for _ in range(28):
        record(manager, AuditAction.PAYMENT_RECORDED)
    client.force_login(manager)
    url = reverse("manage:activity")
    assert len(client.get(url).context["events"]) == 25
    assert len(client.get(url, {"page": 2}).context["events"]) == 3
    for params in (
        {"property": "forged"},
        {"actor": 99999999},
        {"start": "bad"},
        {"start": "2026-02-01", "end": "2026-01-01"},
    ):
        assert client.get(url, params).status_code == 400


def test_activity_projection_query_count_is_bounded():
    manager = make_manager()
    lease = make_lease()
    for _ in range(26):
        record(manager, AuditAction.LEASE_ACTIVATED, obj=lease)
    with CaptureQueriesContext(connection) as queries:
        rows = activity.project(activity.visible(manager)[:25])
    assert len(rows) == 25
    assert len(queries) <= 3


def test_empty_dashboard_has_zeroes_and_safe_links(client):
    manager = make_manager()
    metrics = services.project(manager)["metrics"]
    assert all(metric.value == 0 for metric in metrics.values())
    client.force_login(manager)
    assert client.get(metrics["month-charges"].url).status_code == 200


def test_maintenance_age_followups_and_personal_unread():
    manager = make_manager()
    tenant = make_tenant()
    lease = make_lease(tenants=[tenant])
    ticket = MaintenanceRequest.objects.create(
        property=lease.unit.property,
        unit=lease.unit,
        title="Faucet",
        description="Synthetic",
        category="plumbing",
        reporter=manager,
        status=Status.IN_PROGRESS,
        priority=4,
    )
    MaintenanceRequest.objects.filter(pk=ticket.pk).update(
        created_at=timezone.now() - timedelta(days=8)
    )
    Audience.objects.create(request=ticket, lease=lease, unresolved=True, permission_by=manager)
    from uuid import uuid4

    review, _ = communications.review_conversation(
        actor=tenant, lease=lease, subject="Parking", visibility="PRIVATE"
    )
    message = communications.start_conversation(
        actor=tenant,
        review=review,
        body="Hello",
        files=[],
        token=uuid4(),
        portal_base="http://testserver",
    )
    metrics = services.project(manager)["metrics"]
    for key in ("urgent", "aging", "follow-ups", "in-progress", "needs-reply", "unread"):
        assert metrics[key].value == 1, key
    communications.mark_read(message.conversation, actor=manager, message_id=message.pk)
    metrics = services.project(manager)["metrics"]
    assert metrics["unread"].value == 0
    assert metrics["needs-reply"].value == 1


def test_all_charge_categories_and_inline_credits():
    manager = make_manager()
    lease = make_lease()
    for index, kind in enumerate(
        (
            ChargeKind.RENT,
            ChargeKind.NNN,
            ChargeKind.RESPONSIBILITY,
            ChargeKind.MANUAL,
            ChargeKind.OPENING,
        ),
        start=1,
    ):
        extra = (
            {"responsibility": make_responsibility(lease.unit.property)}
            if kind == ChargeKind.RESPONSIBILITY
            else {}
        )
        make_charge(lease, kind=kind, amount=Decimal(index * 10), **extra)
    ledger.create_adjustment(
        lease.charges.get(kind=ChargeKind.OPENING),
        direction=Direction.DECREASE,
        amount=Decimal("20"),
        reason="Opening correction",
        actor=manager,
    )
    make_charge(lease, kind=ChargeKind.ADJUSTMENT, amount=Decimal("5"), reason="Other adjustment")
    make_payment(lease, amount=Decimal("400"), status=PaymentStatus.VOID)
    metrics = services.project(manager)["metrics"]
    assert metrics["month-charges"].value == Decimal("135")
    assert metrics["month-adjustment"].value == Decimal("5")
    assert metrics["month-opening"].value == Decimal("30")
    assert metrics["month-payments"].value == 0
    assert (
        sum((metrics[f"month-{kind.lower()}"].value for kind in services.CATEGORIES), Decimal("0"))
        == metrics["month-charges"].value
    )


def test_month_boundary_uses_application_timezone():
    manager = make_manager()
    with (
        timezone.override("America/Los_Angeles"),
        patch(
            "apps.dashboard.services.timezone.now",
            return_value=datetime(2026, 11, 1, 0, 30, tzinfo=UTC),
        ),
    ):
        lease = make_lease()
        make_charge(lease, due_date=date(2026, 10, 31), amount=Decimal("31"))
        make_charge(lease, due_date=date(2026, 11, 1), amount=Decimal("1"))
        make_payment(lease, payment_date=date(2026, 10, 31), amount=Decimal("10"))
        make_payment(lease, payment_date=date(2026, 11, 1), amount=Decimal("1"))
        projection = services.project(manager)
    assert projection["groups"][1][0] == "October 2026"
    assert projection["metrics"]["month-charges"].value == 31
    assert projection["metrics"]["month-payments"].value == 10


def test_dashboard_queries_do_not_grow_per_lease():
    manager = make_manager()
    make_charge()
    with CaptureQueriesContext(connection) as initial:
        services.project(manager)
    for _ in range(8):
        make_charge(make_lease(make_unit()))
    with CaptureQueriesContext(connection) as grown:
        services.project(manager)
    assert len(grown) <= len(initial) + 2


def test_detail_pages_are_read_only_and_anonymous_is_redirected(client):
    assert client.get(reverse("manage:activity")).status_code == 302
    manager = make_manager()
    make_charge()
    client.force_login(manager)
    count = AuditEvent.objects.count()
    url = reverse("manage:dashboard-detail", args=["month-charges"])
    assert client.get(url).status_code == 200
    assert client.post(url).status_code == 405
    assert AuditEvent.objects.count() == count
