"""Phase 7: privacy, operational authority, immutable money, and plain-form workflows."""

from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditEvent
from apps.leases.models import LeaseTenant
from apps.ledger.models import Charge, Direction
from apps.ledger.services import create_adjustment
from apps.maintenance import services as s
from apps.maintenance.models import (
    Attachment,
    MaintenanceRequest,
    Notification,
    Recharge,
    Revision,
    Status,
    Update,
    Vendor,
)
from tests.factories import (
    make_admin,
    make_lease,
    make_maintenance,
    make_manager,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quick_test_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@pytest.fixture
def world():
    manager = make_manager()
    tenant = make_tenant(email="one@example.com")
    cotenant = make_tenant(username="cotenant", email="two@example.com")
    other = make_tenant(username="other", email="other@example.com")
    worker = make_maintenance()
    lease = make_lease(tenants=[tenant, cotenant])
    second = make_lease(make_unit(lease.unit.property, identifier="2"), tenants=[other])
    ticket = s.create_request(
        actor=tenant,
        property=lease.unit.property,
        unit=lease.unit,
        lease=lease,
        title="Kitchen leak",
        description="Water below sink",
        category="plumbing",
        portal_base="http://testserver",
    )
    return manager, tenant, cotenant, other, worker, lease, second, ticket


def photo(name="leak.png"):
    data = BytesIO()
    Image.new("RGB", (12, 12)).save(data, format="PNG")
    return SimpleUploadedFile(name, data.getvalue(), content_type="image/png")


def expense(world, **kwargs):
    manager, _, _, _, _, _, _, ticket = world
    return s.record_cost(
        ticket,
        actor=manager,
        amount=Decimal("237.00"),
        description="Plumber invoice",
        incurred_on=timezone.localdate(),
        **kwargs,
    )


def allocation(lease, amount="100.00", reason="Agreed repair charge"):
    return {"lease": lease.pk, "amount": amount, "due": timezone.localdate(), "reason": reason}


def manage(world, status, **kwargs):
    manager, _, _, _, worker, _, _, ticket = world
    return s.change_work(
        ticket, actor=manager, status=status, priority=2, assigned_to=worker, **kwargs
    )


def test_scope_and_public_ids(world, client):
    manager, tenant, cotenant, other, worker, lease, _, ticket = world
    assert isinstance(ticket.pk, int)
    for person, visible in (
        (manager, True),
        (tenant, True),
        (cotenant, True),
        (other, False),
        (worker, False),
    ):
        assert (
            MaintenanceRequest.objects.visible_to(person).filter(pk=ticket.pk).exists() is visible
        )
        client.force_login(person)
        namespace = "tenant_maintenance" if person.is_tenant else "maintenance"
        assert client.get(reverse(f"{namespace}:detail", args=[ticket.public_id])).status_code == (
            200 if visible else 404
        )
    manage(world, Status.ACKNOWLEDGED)
    assert MaintenanceRequest.objects.visible_to(worker).filter(pk=ticket.pk).exists()
    assert AuditEvent.objects.filter(
        object_type="maintenance.MaintenanceRequest", object_id=ticket.pk
    ).exists()
    assert ticket.audiences.get(lease=lease).permission_to_enter is False


def test_shared_property_conversations_do_not_leak(world, client):
    manager, tenant, _, other, _, lease, second, _ = world
    ticket = s.create_request(
        actor=manager,
        property=lease.unit.property,
        title="Roof repair",
        description="PRIVATE insurance note",
        category="structural",
    )
    s.share_request(ticket, actor=manager, lease=lease, introduction="Roof repair notice")
    s.share_request(ticket, actor=manager, lease=second, introduction="Notice for second unit")
    s.add_update(
        ticket,
        actor=tenant,
        lease_id=lease.pk,
        body="PRIVATE first tenant reply",
        files=[photo("private.png")],
    )
    s.add_update(ticket, actor=other, lease_id=second.pk, body="PRIVATE second tenant reply")
    client.force_login(tenant)
    response = client.get(reverse("tenant_maintenance:detail", args=[ticket.public_id]))
    body = response.content.decode()
    assert "PRIVATE first tenant reply" in body
    for private in (
        "PRIVATE second tenant reply",
        "PRIVATE insurance note",
        "Notice for second unit",
        other.username,
    ):
        assert private not in body
    attachment = ticket.updates.get(body="PRIVATE first tenant reply").attachments.get()
    client.force_login(other)
    assert (
        client.get(reverse("tenant_maintenance:download", args=[attachment.public_id])).status_code
        == 404
    )
    s.follow_up(ticket, actor=tenant, lease_id=lease.pk, body="Still leaking")
    ticket.status = Status.CLOSED
    ticket.save()
    response = client.get(reverse("tenant_maintenance:list"))
    assert "Roof repair" not in response.content.decode()


def test_move_out_history_and_new_occupants(world, client):
    manager, tenant, _, other, _, lease, _, ticket = world
    lease.status, lease.ended_on, lease.end_reason = "ENDED", timezone.localdate(), "MUTUAL"
    lease.save()
    newcomer = make_tenant(username="newcomer")
    make_lease(lease.unit, tenants=[newcomer])
    assert MaintenanceRequest.objects.visible_to(tenant).filter(pk=ticket.pk).exists()
    assert not MaintenanceRequest.objects.visible_to(newcomer).exists()
    for method, kwargs in (
        (s.add_update, {"body": "hello"}),
        (s.follow_up, {"body": "hello"}),
        (s.set_entry_permission, {"permission": True}),
    ):
        with pytest.raises(PermissionDenied):
            method(ticket, actor=tenant, lease_id=lease.pk, **kwargs)
    client.force_login(tenant)
    response = client.get(reverse("tenant_maintenance:detail", args=[ticket.public_id]))
    assert response.status_code == 200
    assert "Add update" not in response.content.decode()
    with pytest.raises(ValidationError):
        s.share_request(ticket, actor=manager, lease=lease, introduction="Not current")
    tenant.is_active = False
    tenant.save()
    assert not MaintenanceRequest.objects.visible_to(tenant).exists()


@pytest.mark.parametrize(
    "mode", ["other_property", "wrong_unit", "wrong_lease", "worker", "draft", "ended"]
)
def test_creation_guards(world, mode):
    manager, tenant, _, _, worker, lease, second, _ = world
    kwargs = {
        "actor": tenant,
        "property": lease.unit.property,
        "unit": lease.unit,
        "lease": lease,
        "title": "Leak",
        "description": "Description",
        "category": "plumbing",
    }
    if mode == "other_property":
        kwargs["property"] = make_unit().property
    elif mode == "wrong_unit":
        kwargs["unit"] = second.unit
    elif mode == "wrong_lease":
        kwargs["lease"] = second
    elif mode == "worker":
        kwargs.update(actor=worker, lease=None)
    else:
        lease.status = mode.upper()
        if mode == "ended":
            lease.ended_on, lease.end_reason = timezone.localdate(), "MUTUAL"
        lease.save()
    with pytest.raises((PermissionDenied, ValidationError)):
        s.create_request(**kwargs)


def test_staff_vacant_unit_and_explicit_sharing(world):
    manager, _, _, _, worker, lease, second, _ = world
    vacant = make_unit(lease.unit.property, identifier="vacant")
    ticket = s.create_request(
        actor=manager,
        property=vacant.property,
        unit=vacant,
        title="Paint",
        description="Paint walls",
        category="general",
    )
    assert not ticket.audiences.exists()
    with pytest.raises(ValidationError):
        s.share_request(ticket, actor=manager, lease=second, introduction="hello")
    with pytest.raises(PermissionDenied):
        s.share_request(ticket, actor=worker, lease=lease, introduction="hello")


@pytest.mark.parametrize("status", list(Status.values))
def test_manager_can_skip_stages(world, status):
    ticket = manage(
        world,
        status,
        reason="Waiting for parts" if status == Status.WAITING else "",
        scheduled_for=timezone.now() if status == Status.SCHEDULED else None,
    )
    assert ticket.status == status


def test_transition_guards_and_follow_up(world, client):
    manager, tenant, _, _, worker, lease, _, ticket = world
    with pytest.raises(ValidationError):
        manage(world, Status.SCHEDULED)
    with pytest.raises(ValidationError):
        manage(world, Status.WAITING)
    manage(world, Status.COMPLETED)
    with pytest.raises(ValidationError):
        manage(world, Status.OPEN)
    with pytest.raises(PermissionDenied):
        s.change_work(
            ticket, actor=worker, status=Status.IN_PROGRESS, priority=2, assigned_to=worker
        )
    manage(world, Status.CLOSED)
    s.follow_up(ticket, actor=tenant, lease_id=lease.pk, body="Not resolved")
    ticket.refresh_from_db()
    assert ticket.status == Status.CLOSED
    assert ticket.audiences.get().unresolved
    client.force_login(manager)
    response = client.get(reverse("maintenance:list"))
    assert "Unresolved follow-up — needs manager review" in response.content.decode()
    s.review_follow_up(ticket, actor=manager, lease_id=lease.pk, body="We will return")
    assert not ticket.audiences.get().unresolved
    manage(world, Status.IN_PROGRESS, reason="Tenant reports unresolved leak")


def test_worker_limits_and_note_revisions(world):
    manager, tenant, _, _, worker, lease, _, ticket = world
    manage(world, Status.ACKNOWLEDGED)
    ticket = s.change_work(
        ticket, actor=worker, status=Status.IN_PROGRESS, priority=2, assigned_to=worker
    )
    with pytest.raises(PermissionDenied):
        s.change_work(ticket, actor=worker, status=Status.CLOSED, priority=2, assigned_to=worker)
    with pytest.raises(PermissionDenied):
        s.change_work(
            ticket, actor=worker, status=Status.IN_PROGRESS, priority=4, assigned_to=worker
        )
    update = s.add_update(ticket, actor=worker, body="First internal note")
    s.edit_update(update, actor=worker, body="Corrected note", reason="Typo")
    update.refresh_from_db()
    assert update.revisions.get().previous_body == "First internal note"
    s.edit_update(update, actor=manager, body="Manager correction", reason="Verified repair")
    assert Revision.objects.filter(update=update).count() == 2
    with pytest.raises(PermissionDenied):
        s.edit_update(update, actor=tenant, body="Forged edit", reason="none")
    with pytest.raises(ValidationError):
        update.lease = lease
        update.save()
    update.refresh_from_db()
    public = s.publish_update(update, actor=manager, lease=lease)
    assert public.lease_id == lease.pk
    assert update.lease_id is None
    assert public.body == "Manager correction"
    with pytest.raises(PermissionDenied):
        s.publish_update(update, actor=worker, lease=lease)


def test_permission_actor_and_time(world):
    manager, tenant, _, _, worker, lease, _, ticket = world
    original = ticket.audiences.get().permission_at
    s.set_entry_permission(ticket, actor=tenant, lease_id=lease.pk, permission=True)
    audience = ticket.audiences.get()
    assert audience.permission_to_enter and audience.permission_by == tenant
    assert audience.permission_at >= original
    manage(world, Status.ACKNOWLEDGED)
    with pytest.raises(PermissionDenied):
        s.set_entry_permission(ticket, actor=worker, lease_id=lease.pk, permission=True)
    s.set_entry_permission(
        ticket,
        actor=manager,
        lease_id=lease.pk,
        permission=False,
        source_note="Tenant withdrew authorization by phone.",
    )
    assert ticket.audiences.get().permission_by == manager


def test_scheduling_by_time_window(world):
    ticket = manage(world, Status.SCHEDULED, schedule_window="Oct 20, 2026, 9 AM–noon")
    assert ticket.scheduled_for is None
    assert ticket.schedule_window == "Oct 20, 2026, 9 AM–noon"


def test_photo_download_and_removal(world, client, django_capture_on_commit_callbacks):
    manager, tenant, cotenant, other, worker, lease, _, ticket = world
    update = s.add_update(
        ticket, actor=tenant, lease_id=lease.pk, body="Photo", files=[photo("My sink.png")]
    )
    attachment = update.attachments.get()
    assert "My sink" not in attachment.file.name
    manage(world, Status.ACKNOWLEDGED)
    for actor, allowed in ((tenant, True), (cotenant, True), (other, False), (worker, True)):
        client.force_login(actor)
        namespace = "tenant_maintenance" if actor.is_tenant else "maintenance"
        response = client.get(reverse(f"{namespace}:download", args=[attachment.public_id]))
        assert response.status_code == (200 if allowed else 404)
        if allowed:
            assert "My sink.png" in response["Content-Disposition"]
            assert response["X-Content-Type-Options"] == "nosniff"
            assert b"".join(response.streaming_content)
    with pytest.raises(PermissionDenied):
        s.remove_attachment(attachment, actor=manager, reason="wrong file")
    admin = make_admin()
    with django_capture_on_commit_callbacks(execute=True):
        s.remove_attachment(attachment, actor=admin, reason="Wrong sink")
    attachment.refresh_from_db()
    assert attachment.removed_by == admin and attachment.removal_reason == "Wrong sink"
    assert not attachment.file.storage.exists(attachment.file.name)
    assert (
        client.get(reverse("maintenance:download", args=[attachment.public_id])).status_code == 404
    )


@pytest.mark.parametrize("mode", ["too_many", "bad_image", "pdf", "oversize"])
def test_upload_guards(world, mode):
    manager, tenant, _, _, _, lease, _, ticket = world
    files = [photo()]
    if mode == "too_many":
        files = [photo(f"{i}.png") for i in range(11)]
    elif mode == "bad_image":
        files = [SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")]
    elif mode == "pdf":
        files = [SimpleUploadedFile("bill.pdf", b"%PDF-1.7", content_type="application/pdf")]
    else:
        files[0].size = 6 * 1024 * 1024
    before = ticket.updates.count()
    with pytest.raises(ValidationError):
        s.add_update(ticket, actor=tenant, lease_id=lease.pk, body="Photo", files=files)
    assert ticket.updates.count() == before
    assert not Attachment.objects.exists()


def test_cost_evidence_and_immutable_corrections(world, client):
    manager, tenant, _, _, worker, _, _, ticket = world
    cost = expense(
        world,
        files=[
            SimpleUploadedFile("Invoice.pdf", b"%PDF-1.7\nInvoice", content_type="application/pdf")
        ],
    )
    correction = s.record_cost(
        ticket,
        actor=manager,
        amount="37.00",
        direction="DECREASE",
        corrects=cost,
        reason="Vendor credit",
        description="Credit",
        incurred_on=timezone.localdate(),
    )
    assert cost.net_amount == Decimal("200.00")
    assert cost.amount == Decimal("237.00")
    with pytest.raises(ValidationError):
        cost.save()
    with pytest.raises(ValidationError):
        correction.delete()
    with pytest.raises(PermissionDenied):
        s.record_cost(
            ticket, actor=worker, amount="10", description="bad", incurred_on=timezone.localdate()
        )
    manage(world, Status.ACKNOWLEDGED)
    attachment = cost.attachments.get()
    for person in (tenant, worker):
        client.force_login(person)
        ns = "tenant_maintenance" if person.is_tenant else "maintenance"
        assert client.get(reverse(f"{ns}:download", args=[attachment.public_id])).status_code == 404
        assert (
            "Plumber invoice"
            not in client.get(reverse(f"{ns}:detail", args=[ticket.public_id])).content.decode()
        )
    client.force_login(manager)
    response = client.get(reverse("maintenance:download", args=[attachment.public_id]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content)


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "1.001", "10000000000", "bad"])
def test_invalid_money(world, amount):
    with pytest.raises(ValidationError):
        s.record_cost(
            world[-1],
            actor=world[0],
            amount=amount,
            description="Bad",
            incurred_on=timezone.localdate(),
        )


def test_review_confirmation_idempotency_and_net_adjustments(world):
    manager, _, _, _, _, lease, _, ticket = world
    cost = expense(world)
    review = s.review_recharge(cost, actor=manager, allocations=[allocation(lease, "300.00")])
    assert not Recharge.objects.exists() and not Charge.objects.exists()
    rows = s.confirm_recharge(cost, actor=manager, token=review)
    assert len(rows) == 1 and rows[0].charge.amount == Decimal("300.00")
    assert s.confirm_recharge(cost, actor=manager, token=review)[0].pk == rows[0].pk
    assert Recharge.objects.count() == Charge.objects.count() == 1
    create_adjustment(
        rows[0].charge,
        direction=Direction.DECREASE,
        amount=Decimal("20.00"),
        reason="Credit",
        actor=manager,
    )
    assert s.net_recharges(cost) == Decimal("280.00")
    assert cost.amount == Decimal("237.00")


@pytest.mark.parametrize(
    "mode",
    ["cost", "prior_charge", "ended", "draft", "settled", "tampered", "other_actor", "roster"],
)
def test_stale_review_and_forgery(world, mode):
    manager, _, _, _, _, lease, _, ticket = world
    cost = expense(world)
    if mode == "prior_charge":
        first = s.review_recharge(cost, actor=manager, allocations=[allocation(lease)])
        first_charge = s.confirm_recharge(cost, actor=manager, token=first)[0].charge
    review = s.review_recharge(cost, actor=manager, allocations=[allocation(lease)])
    actor = manager
    if mode == "cost":
        s.record_cost(
            ticket,
            actor=manager,
            amount="1.00",
            description="Correction",
            corrects=cost,
            incurred_on=timezone.localdate(),
            reason="Updated invoice",
        )
    elif mode == "prior_charge":
        create_adjustment(
            first_charge,
            direction=Direction.DECREASE,
            amount=Decimal("1.00"),
            reason="Credit",
            actor=manager,
        )
    elif mode in ("ended", "draft", "settled"):
        lease.status = "ENDED" if mode != "draft" else "DRAFT"
        if mode != "draft":
            lease.ended_on, lease.end_reason = timezone.localdate(), "MUTUAL"
        if mode == "settled":
            lease.account_status = "SETTLED"
            lease.settled_at = timezone.now()
            lease.settled_by = manager
        lease.save()
    elif mode == "roster":
        newcomer = make_tenant(username="review-roster-change")
        LeaseTenant.objects.create(lease=lease, tenant=newcomer)
    elif mode == "tampered":
        review += "tamper"
    else:
        actor = make_admin()
    before = Recharge.objects.count()
    with pytest.raises((ValidationError, PermissionDenied)):
        s.confirm_recharge(cost, actor=actor, token=review)
    assert Recharge.objects.count() == before


def test_property_manual_split_and_transactional_rollback(world):
    manager, _, _, _, _, lease, second, _ = world
    ticket = s.create_request(
        actor=manager,
        property=lease.unit.property,
        title="Shared repair",
        description="Roof",
        category="structural",
    )
    cost = s.record_cost(
        ticket,
        actor=manager,
        amount="100",
        description="Roof invoice",
        incurred_on=timezone.localdate(),
    )
    review = s.review_recharge(
        cost, actor=manager, allocations=[allocation(lease, "25"), allocation(second, "75")]
    )
    original = s.create_charge
    calls = 0

    def failure(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValidationError("Simulated second write failure")
        return original(*args, **kwargs)

    with patch.object(s, "create_charge", side_effect=failure), pytest.raises(ValidationError):
        s.confirm_recharge(cost, actor=manager, token=review)
    assert not Charge.objects.exists() and not Recharge.objects.exists()
    rows = s.confirm_recharge(cost, actor=manager, token=review)
    assert [row.charge.amount for row in rows] == [Decimal("25"), Decimal("75")]


def test_invalid_recharge_targets_and_split(world):
    manager, _, _, _, _, lease, second, _ = world
    cost = expense(world)
    for rows in (
        [],
        [allocation(second)],
        [allocation(lease), allocation(lease)],
        [allocation(lease, reason="")],
    ):
        with pytest.raises(ValidationError):
            s.review_recharge(cost, actor=manager, allocations=rows)


def test_notifications_after_commit_privacy_and_retry(world, django_capture_on_commit_callbacks):
    manager, tenant, cotenant, other, worker, lease, _, ticket = world
    Notification.objects.all().delete()
    with override_settings(
        MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    ):
        with django_capture_on_commit_callbacks(execute=True):
            s.add_update(
                ticket,
                actor=manager,
                lease_id=lease.pk,
                body="SECRET note body",
                portal_base="http://testserver",
            )
        assert len(mail.outbox) == 2
        for message in mail.outbox:
            assert "SECRET" not in message.body
            assert str(ticket.public_id) in message.body
            assert other.email not in message.to
        before = len(mail.outbox)
        with django_capture_on_commit_callbacks(execute=True):
            s.add_update(ticket, actor=manager, body="INTERNAL SECRET")
        assert len(mail.outbox) == before
        with patch.object(s, "send_mail", side_effect=RuntimeError("private server error")):
            with django_capture_on_commit_callbacks(execute=True):
                update = s.add_update(
                    ticket, actor=manager, lease_id=lease.pk, body="Saved despite mail failure"
                )
        assert Update.objects.filter(pk=update.pk).exists()
        notice = update.notifications.first()
        assert notice.status == "FAILED" and "private server" not in notice.last_error
        with django_capture_on_commit_callbacks(execute=True):
            s.retry_notification(notice, actor=manager)
        notice.refresh_from_db()
        assert notice.status == "SENT" and notice.attempts == 2
        assert list(notice.deliveries.values_list("outcome", flat=True)) == ["FAILED", "SENT"]
        with pytest.raises(PermissionDenied):
            s.retry_notification(notice, actor=worker)
        s.deliver(notice.pk)
        notice.refresh_from_db()
        assert notice.attempts == 2


def test_notification_recipient_rechecked(world):
    _, tenant, _, _, _, _, _, _ = world
    notice = Notification.objects.filter(recipient=tenant).first()
    tenant.is_active = False
    tenant.save()
    s.deliver(notice.pk)
    notice.refresh_from_db()
    assert notice.status == "SKIPPED"


@pytest.mark.parametrize(
    "action", ["update", "work", "share", "permission", "cost", "review-follow-up"]
)
def test_manager_form_rendering(world, client, action):
    manager, _, _, _, _, _, _, ticket = world
    client.force_login(manager)
    assert (
        client.get(reverse("maintenance:action", args=[ticket.public_id, action])).status_code
        == 200
    )


def test_plain_form_end_to_end_and_back_writes_nothing(world, client):
    manager, tenant, _, _, worker, lease, _, ticket = world
    client.force_login(tenant)
    assert client.get(reverse("tenant_maintenance:create")).status_code == 200
    response = client.post(
        reverse("tenant_maintenance:create"),
        {
            "lease": lease.pk,
            "location": "unit",
            "title": "Broken latch",
            "category": "security",
            "description": "Latch is loose",
            "permission": "",
        },
    )
    assert response.status_code == 302
    request = MaintenanceRequest.objects.get(title="Broken latch")
    client.force_login(manager)
    assert (
        client.post(
            reverse("maintenance:action", args=[request.public_id, "work"]),
            {
                "status": Status.SCHEDULED,
                "priority": 3,
                "assigned_to": worker.pk,
                "scheduled_for": "2026-10-20T09:00",
                "schedule_window": "9 AM–noon",
            },
        ).status_code
        == 302
    )
    client.force_login(worker)
    for status in (Status.IN_PROGRESS, Status.COMPLETED):
        assert (
            client.post(
                reverse("maintenance:action", args=[request.public_id, "work"]), {"status": status}
            ).status_code
            == 302
        )
    client.force_login(manager)
    request.refresh_from_db()
    s.change_work(request, actor=manager, status=Status.CLOSED, priority=3, assigned_to=worker)
    client.force_login(tenant)
    audience = request.audiences.get()
    assert (
        client.post(
            reverse("tenant_maintenance:action", args=[request.public_id, "follow-up"]),
            {"audience": audience.pk, "body": "Latch still sticks"},
        ).status_code
        == 302
    )
    client.force_login(manager)
    cost = expense(world)
    url = reverse("maintenance:recharge", args=[ticket.public_id, cost.pk])
    post = {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "100",
        "form-0-lease": lease.pk,
        "form-0-amount": "20.00",
        "form-0-due": timezone.localdate().isoformat(),
        "form-0-reason": "Agreed latch repair",
    }
    response = client.post(url, post)
    assert response.status_code == 200
    token = response.context["review"]
    assert not Charge.objects.exists()
    assert client.post(url, {"review": token, "back": "yes"}).status_code == 200
    assert not Charge.objects.exists()
    response = client.post(url, {"review": token, "confirm": "yes"})
    assert response.status_code == 302
    assert Charge.objects.get().amount == Decimal("20")
    assert client.get(reverse("maintenance:detail", args=[ticket.public_id])).status_code == 200


@pytest.mark.parametrize("page", ["list", "create", "vendors"])
def test_manager_pages(world, client, page):
    client.force_login(world[0])
    assert client.get(reverse(f"maintenance:{page}")).status_code == 200


def test_worker_and_tenant_http_denials(world, client):
    manager, tenant, _, other, worker, lease, _, ticket = world
    manage(world, Status.ACKNOWLEDGED)
    for actor, ns, actions in (
        (worker, "maintenance", ["share", "cost", "permission", "review-follow-up"]),
        (tenant, "tenant_maintenance", ["work", "share", "cost", "review-follow-up"]),
    ):
        client.force_login(actor)
        for action in actions:
            response = client.post(reverse(f"{ns}:action", args=[ticket.public_id, action]), {})
            # Worker permission form itself is unavailable, not merely its submit handler.
            assert response.status_code == 403
    client.force_login(worker)
    assert client.get(reverse("maintenance:create")).status_code == 403
    assert client.get(reverse("maintenance:vendors")).status_code == 403
    client.force_login(tenant)
    assert client.get(reverse("maintenance:list")).status_code == 403
    assert client.get(reverse("tenant_maintenance:detail", args=[uuid4()])).status_code == 404


def test_vendor_retirement_and_model_guards(world, client):
    manager, _, _, _, _, _, _, ticket = world
    client.force_login(manager)
    assert (
        client.post(
            reverse("maintenance:vendors"),
            {
                "name": "Quality Plumbing",
                "contact": "555-0100",
                "trades": "Plumbing",
                "is_active": "on",
            },
        ).status_code
        == 302
    )
    vendor = Vendor.objects.get()
    assert (
        client.post(
            reverse("maintenance:vendor-edit", args=[vendor.pk]),
            {"name": vendor.name, "contact": vendor.contact, "trades": vendor.trades},
        ).status_code
        == 302
    )
    vendor.refresh_from_db()
    assert not vendor.is_active
    with pytest.raises(ValidationError):
        ticket.delete()
    with pytest.raises(ValidationError):
        ticket.updates.first().delete()
    with transaction.atomic(), pytest.raises(IntegrityError):
        MaintenanceRequest.objects.filter(pk=ticket.pk).update(
            status=Status.SCHEDULED, scheduled_for=None
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_confirmation_posts_once(world):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    manager, _, _, _, _, lease, _, _ = world
    cost = expense(world)
    token = s.review_recharge(cost, actor=manager, allocations=[allocation(lease)])
    ready = Barrier(2)

    def confirm():
        try:
            ready.wait(timeout=10)
            return s.confirm_recharge(cost, actor=manager, token=token)[0].pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: confirm(), range(2)))
    assert results[0] == results[1]
    assert Charge.objects.count() == Recharge.objects.count() == 1


def test_storage_rolls_back_on_insert_failure(world, media_root):
    _, tenant, _, _, _, lease, _, ticket = world
    with patch.object(Attachment, "save", side_effect=IntegrityError("Simulated failure")):
        with pytest.raises(IntegrityError):
            s.add_update(
                ticket, actor=tenant, lease_id=lease.pk, body="failed photo", files=[photo()]
            )
    assert not ticket.updates.filter(body="failed photo").exists()
    assert not list(media_root.rglob("*.png"))


def test_forged_audience_and_note_correction_cannot_leak(world, client):
    manager, tenant, _, other, worker, lease, second, ticket = world
    client.force_login(tenant)
    response = client.post(
        reverse("tenant_maintenance:action", args=[ticket.public_id, "update"]),
        {"audience": 999999, "body": "Forged"},
    )
    assert response.status_code == 200 and "Select a valid choice" in response.content.decode()
    assert not ticket.updates.filter(body="Forged").exists()
    with pytest.raises(ValidationError):
        s.add_update(ticket, actor=manager, lease_id=second.pk, body="Wrong audience")
    note = s.add_update(ticket, actor=manager, body="Internal")
    manage(world, Status.ACKNOWLEDGED)
    with pytest.raises(PermissionDenied):
        s.edit_update(note, actor=worker, body="Edited other's note", reason="Unauthorized")
    client.force_login(worker)
    assert (
        client.get(
            reverse("maintenance:update-action", args=[ticket.public_id, note.pk, "publish"])
        ).status_code
        == 403
    )
