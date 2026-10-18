"""Authorized maintenance operations. Views and previews never decide liability."""

from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.files import validate_document_upload
from apps.common.images import validate_image_upload
from apps.leases.models import Lease, LeaseTenant
from apps.ledger.services import create_charge

from .models import (
    CATEGORIES,
    Attachment,
    Audience,
    Cost,
    MaintenanceRequest,
    Notification,
    NotificationAttempt,
    Priority,
    Recharge,
    Revision,
    Status,
    Update,
)

ZERO = Decimal("0.00")
SALT = "maintenance-recharge-v1"
_uploads = ContextVar("maintenance_uploads", default=None)


def file_transaction(function):
    """Roll storage back too if saving the database transaction fails."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        files = []
        token = _uploads.set(files)
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except Exception:
            for file in files:
                file.delete(save=False)
            raise
        finally:
            _uploads.reset(token)

    return wrapped


def manager(actor):
    if not actor.is_active or not actor.is_manager_or_above:
        raise PermissionDenied


def authorized(request, actor):
    if not MaintenanceRequest.objects.visible_to(actor).filter(pk=request.pk).exists():
        raise PermissionDenied


def current(lease):
    return Lease.objects.current().filter(pk=lease.pk).exists()


def tenant_audience(request, actor, lease_id):
    authorized(request, actor)
    audience = request.audiences.filter(lease_id=lease_id).first()
    if audience is None:
        raise ValidationError("Choose a tenancy already shared on this request.")
    if actor.is_tenant:
        audience.lease = Lease.objects.select_for_update().get(pk=audience.lease_id)
        if not audience.lease.lease_tenants.filter(tenant=actor).exists() or not current(
            audience.lease
        ):
            raise PermissionDenied("Former tenancies have read-only maintenance history.")
    return audience


def log(request, actor, summary, **facts):
    record(
        actor=actor, action=AuditAction.MAINTENANCE_CHANGED, obj=request, summary=summary, **facts
    )


def touch(request):
    request.revision += 1
    request.save()


def validate_files(files, *, invoices=False):
    files = list(files)
    if len(files) > 10:
        raise ValidationError("Upload no more than ten files at a time.")
    limit = settings.RHP_MAX_UPLOAD_MB * 1024 * 1024
    for upload in files:
        if invoices and upload.name.lower().endswith(".pdf"):
            validate_document_upload(upload, max_bytes=limit, allowed={".pdf"})
            if not upload.read(5).startswith(b"%PDF-"):
                raise ValidationError("Upload a valid PDF invoice or receipt.")
            upload.seek(0)
        else:
            validate_image_upload(upload, max_bytes=limit)
            with Image.open(upload) as image:
                if image.format not in ("JPEG", "PNG", "WEBP") or Path(
                    upload.name
                ).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    raise ValidationError("Upload a JPEG, PNG, or WebP photo.")
            upload.seek(0)
    return files


def attach(files, *, update=None, cost=None):
    # Validate the whole submission before writing any bytes. Clean partial storage writes.
    saved = []
    try:
        for upload in files:
            row = Attachment(update=update, cost=cost, original_name=upload.name)
            row.file.save(upload.name, upload, save=False)
            if _uploads.get() is not None:
                _uploads.get().append(row.file)
            saved.append(row)
            row.save()
    except Exception:
        for row in saved:
            row.file.delete(save=False)
        raise
    return saved


def queue_notifications(update, portal_base):
    if not update.lease_id:
        return
    url = portal_base.rstrip("/") + reverse(
        "tenant_maintenance:detail", args=[update.request.public_id]
    )
    for user in (
        User.objects.filter(
            lease_memberships__lease=update.lease,
            is_active=True,
            role=Role.TENANT,
        )
        .exclude(email="")
        .distinct()
    ):
        notice, _ = Notification.objects.get_or_create(
            update=update, recipient=user, defaults={"portal_url": url}
        )
        transaction.on_commit(lambda pk=notice.pk: deliver(pk), robust=True)


def deliver(pk):
    """Durable attempt, neutral email, fresh recipient authorization; errors never undo work."""
    with transaction.atomic():
        notice = (
            Notification.objects.select_for_update()
            .select_related("update__request", "recipient")
            .get(pk=pk)
        )
        if notice.status == "SENT":
            return
        notice.attempts += 1
        if (
            not notice.recipient.is_tenant
            or not Update.objects.visible_to(notice.recipient).filter(pk=notice.update_id).exists()
        ):
            notice.status = "SKIPPED"
            notice.last_error = "Recipient no longer has access."
        else:
            try:
                result = send_mail(
                    "RHP maintenance request update",
                    "Your maintenance request has an update. Sign in to view it:\n"
                    f"{notice.portal_url}\n\nThe portal is not an emergency-dispatch service. "
                    "For immediate danger, call 911.",
                    settings.DEFAULT_FROM_EMAIL,
                    [notice.recipient.email],
                )
                if not result:
                    raise RuntimeError("Mail backend did not accept the message")
                notice.status, notice.sent_at, notice.last_error = "SENT", timezone.now(), ""
            except Exception:
                notice.status, notice.last_error = (
                    "FAILED",
                    "Email could not be sent. Review mail service settings, then retry.",
                )
        NotificationAttempt.objects.create(
            notification=notice, outcome=notice.status, error=notice.last_error
        )
        notice.save()


@transaction.atomic
def retry_notification(notice, *, actor):
    manager(actor)
    transaction.on_commit(lambda: deliver(notice.pk), robust=True)


@file_transaction
def create_request(
    *,
    actor,
    property,
    unit=None,
    lease=None,
    title,
    description,
    category,
    permission=False,
    files=(),
    portal_base="",
):
    if not actor.is_active:
        raise PermissionDenied
    if unit and unit.property_id != property.pk:
        raise ValidationError("Choose a unit at this property.")
    if actor.is_tenant:
        if lease:
            lease = Lease.objects.select_for_update().get(pk=lease.pk)
        if not lease or not current(lease) or not lease.lease_tenants.filter(tenant=actor).exists():
            raise PermissionDenied
        if lease.unit.property_id != property.pk or (unit and unit.pk != lease.unit_id):
            raise PermissionDenied
    else:
        manager(actor)
        if lease is not None:
            raise ValidationError("Staff requests start internal. Share with a tenancy separately.")
    if not title.strip() or not description.strip() or category not in dict(CATEGORIES):
        raise ValidationError("Enter a title, description, and maintenance category.")
    files = validate_files(files)
    request = MaintenanceRequest.objects.create(
        reporter=actor,
        property=property,
        unit=unit,
        reporting_lease=lease,
        title=title.strip(),
        description=description.strip(),
        category=category,
    )
    if lease:
        Audience.objects.create(
            request=request, lease=lease, permission_to_enter=permission, permission_by=actor
        )
    update = Update.objects.create(
        request=request, lease=lease, author=actor, body=description.strip(), kind="SUBMITTED"
    )
    log(request, actor, "Maintenance request submitted.", permission_to_enter=permission)
    queue_notifications(update, portal_base)
    attach(files, update=update)  # Last operation: no DB work after file writes.
    return request


@transaction.atomic
def share_request(request, *, actor, lease, introduction, portal_base=""):
    manager(actor)
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    lease = Lease.objects.select_for_update().get(pk=lease.pk)
    if lease.unit.property_id != request.property_id or (
        request.unit_id and lease.unit_id != request.unit_id
    ):
        raise ValidationError("Share only with a tenancy at the affected property or unit.")
    if not current(lease) or not introduction.strip():
        raise ValidationError("Choose a current tenancy and explain the work to them.")
    if request.audiences.filter(lease=lease).exists():
        raise ValidationError("This tenancy already has access.")
    Audience.objects.create(request=request, lease=lease, permission_by=actor)
    update = Update.objects.create(
        request=request, lease=lease, author=actor, body=introduction.strip(), kind="SHARED"
    )
    touch(request)
    log(request, actor, "Maintenance request shared with a tenancy.", shared_lease=lease.pk)
    queue_notifications(update, portal_base)
    return update


@file_transaction
def add_update(request, *, actor, body, lease_id=None, files=(), portal_base=""):
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    authorized(request, actor)
    if not body.strip():
        raise ValidationError("Enter an update.")
    if actor.is_tenant and not lease_id:
        raise PermissionDenied
    if lease_id:
        tenant_audience(request, actor, lease_id)
    files = validate_files(files)
    update = Update.objects.create(
        request=request, lease_id=lease_id, author=actor, body=body.strip()
    )
    touch(request)
    log(
        request,
        actor,
        "Maintenance update added.",
        update=update.pk,
        audience=lease_id or "internal",
    )
    queue_notifications(update, portal_base)
    attach(files, update=update)
    return update


@transaction.atomic
def edit_update(update, *, actor, body, reason):
    request = MaintenanceRequest.objects.select_for_update().get(pk=update.request_id)
    authorized(request, actor)
    update = Update.objects.select_for_update().get(pk=update.pk)
    if (
        actor.is_tenant
        or update.author.is_tenant
        or (actor.pk != update.author_id and not actor.is_manager_or_above)
    ):
        raise PermissionDenied
    if not body.strip() or not reason.strip():
        raise ValidationError("Enter the corrected update and a reason.")
    Revision.objects.create(
        update=update, actor=actor, previous_body=update.body, reason=reason.strip()
    )
    update.body, update.edited_at = body.strip(), timezone.now()
    update.save()
    touch(request)
    log(request, actor, "Maintenance update corrected.", update=update.pk, reason=reason)
    return update


@transaction.atomic
def publish_update(update, *, actor, lease, portal_base=""):
    manager(actor)
    if update.lease_id is not None:
        raise ValidationError("Only internal notes can be published as a new update.")
    return add_update(
        update.request, actor=actor, body=update.body, lease_id=lease.pk, portal_base=portal_base
    )


@transaction.atomic
def change_work(
    request,
    *,
    actor,
    status,
    reason="",
    assigned_to=None,
    vendor=None,
    priority=None,
    scheduled_for=None,
    schedule_window="",
    portal_base="",
):
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    authorized(request, actor)
    if actor.is_tenant:
        raise PermissionDenied
    if status not in Status.values:
        raise ValidationError("Choose a maintenance status.")
    if not actor.is_manager_or_above:
        if status not in (Status.IN_PROGRESS, Status.WAITING, Status.COMPLETED):
            raise PermissionDenied
        if request.status in (Status.COMPLETED, Status.CLOSED):
            raise PermissionDenied("A manager must reopen completed work.")
        if (
            assigned_to != request.assigned_to
            or vendor != request.vendor
            or priority != request.priority
        ):
            raise PermissionDenied
        if scheduled_for != request.scheduled_for or schedule_window != request.schedule_window:
            raise PermissionDenied
    order = list(Status.values)
    if order.index(status) < order.index(request.status) and not reason.strip():
        raise ValidationError("Explain why work is being reopened or moved backward.")
    if status == Status.WAITING and not reason.strip():
        raise ValidationError("Explain what the work is waiting for.")
    if status == Status.SCHEDULED and scheduled_for is None and not schedule_window.strip():
        raise ValidationError("Enter a scheduled date/time or a time window.")
    if assigned_to and (not assigned_to.is_active or not assigned_to.is_rhp_staff):
        raise ValidationError("Assign an active RHP staff member.")
    if vendor and not vendor.is_active and vendor.pk != request.vendor_id:
        raise ValidationError("Choose an active vendor.")
    if priority not in Priority.values:
        raise ValidationError("Choose a priority.")
    old = request.status
    request.status, request.priority, request.assigned_to, request.vendor = (
        status,
        priority,
        assigned_to,
        vendor,
    )
    request.scheduled_for, request.schedule_window = scheduled_for, schedule_window
    touch(request)
    Update.objects.create(
        request=request,
        author=actor,
        kind="STATUS",
        body=f"{Status(old).label} → {Status(status).label}. {reason}".strip(),
    )
    if old != status:
        for audience in request.audiences.all():
            update = Update.objects.create(
                request=request,
                lease=audience.lease,
                author=actor,
                kind="STATUS",
                body=f"Work status changed from {Status(old).label} to {Status(status).label}.",
            )
            queue_notifications(update, portal_base)
    if actor.is_manager_or_above and old != status:
        request.audiences.update(unresolved=False)
    log(
        request,
        actor,
        f"Work status: {Status(status).label}.",
        previous=old,
        reason=reason,
        assigned_to=assigned_to.pk if assigned_to else None,
        priority=priority,
        scheduled_for=scheduled_for,
    )
    return request


@transaction.atomic
def follow_up(request, *, actor, lease_id, body):
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    if not actor.is_tenant:
        raise PermissionDenied
    audience = tenant_audience(request, actor, lease_id)
    if not body.strip():
        raise ValidationError("Explain what remains unresolved.")
    audience.unresolved = True
    audience.save()
    Update.objects.create(
        request=request, lease_id=lease_id, author=actor, body=body.strip(), kind="UNRESOLVED"
    )
    touch(request)
    log(request, actor, "Tenant reported unresolved work.", audience=lease_id)


@transaction.atomic
def review_follow_up(request, *, actor, lease_id, body, portal_base=""):
    manager(actor)
    update = add_update(request, actor=actor, body=body, lease_id=lease_id, portal_base=portal_base)
    request.audiences.filter(lease_id=lease_id).update(unresolved=False)
    return update


@transaction.atomic
def set_entry_permission(request, *, actor, lease_id, permission, source_note=""):
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    if not actor.is_tenant:
        manager(actor)
        if not source_note.strip() or len(source_note) > 1000:
            raise ValidationError(
                "Record how the tenant's authorization or withdrawal was received."
            )
    audience = tenant_audience(request, actor, lease_id)
    audience.permission_to_enter, audience.permission_by, audience.permission_at = (
        permission,
        actor,
        timezone.now(),
    )
    audience.save()
    Update.objects.create(
        request=request,
        lease_id=lease_id,
        author=actor,
        kind="PERMISSION",
        body=(
            f"Tenant-authorized entry: {'Yes' if permission else 'No'}. "
            "Applies to RHP staff and assigned repair professionals for this request."
        ),
    )
    touch(request)
    log(
        request,
        actor,
        "Tenant entry authorization updated.",
        audience=lease_id,
        permission=permission,
        source_note=source_note.strip() if not actor.is_tenant else "",
    )


def money(value):
    try:
        amount = Decimal(str(value))
        if (
            not amount.is_finite()
            or amount <= ZERO
            or amount != amount.quantize(Decimal("0.01"))
            or amount >= Decimal("10000000000")
        ):
            raise InvalidOperation
        return amount
    except InvalidOperation, ValueError, TypeError:
        raise ValidationError(
            "Enter a positive dollar amount with no more than two decimal places."
        ) from None


@file_transaction
def record_cost(
    request,
    *,
    actor,
    amount,
    description,
    incurred_on,
    vendor=None,
    reference="",
    corrects=None,
    direction="INCREASE",
    reason="",
    files=(),
):
    manager(actor)
    request = MaintenanceRequest.objects.select_for_update().get(pk=request.pk)
    if not description.strip() or not incurred_on:
        raise ValidationError("Describe the repair expense and enter its date.")
    if direction not in ("INCREASE", "DECREASE") or (direction == "DECREASE" and not corrects):
        raise ValidationError("Reductions must correct a recorded expense.")
    if corrects and (
        corrects.request_id != request.pk or corrects.corrects_id or not reason.strip()
    ):
        raise ValidationError(
            "Choose an original expense on this request and explain the correction."
        )
    files = validate_files(files, invoices=True)
    cost = Cost.objects.create(
        request=request,
        actor=actor,
        amount=money(amount),
        description=description.strip(),
        incurred_on=incurred_on,
        vendor=vendor,
        reference=reference,
        corrects=corrects,
        direction=direction,
        reason=reason.strip(),
    )
    touch(request)
    record(
        actor=actor,
        action=AuditAction.MAINTENANCE_COST,
        obj=cost,
        summary="Repair expense correction recorded." if corrects else "Repair expense recorded.",
        amount=cost.effect,
        reason=reason,
    )
    attach(files, cost=cost)
    return cost


def net_recharges(cost):
    return sum(
        (
            row.charge.balance_effect
            + sum((adjustment.balance_effect for adjustment in row.charge.adjustments.all()), ZERO)
            for row in cost.recharges.select_related("charge").prefetch_related(
                "charge__adjustments"
            )
        ),
        ZERO,
    )


def eligible_leases(request):
    rows = Lease.objects.current().filter(
        unit__property_id=request.property_id, account_status="OPEN"
    )
    if request.unit_id:
        rows = rows.filter(unit_id=request.unit_id)
    return rows


def snapshot(cost):
    request = MaintenanceRequest.objects.get(pk=cost.request_id)
    cost = Cost.objects.get(pk=cost.pk)
    return {
        "revision": request.revision,
        "cost": str(cost.net_amount),
        "recharged": str(net_recharges(cost)),
        "leases": [
            [
                row.pk,
                row.status,
                row.account_status,
                row.start_date.isoformat(),
                row.end_date.isoformat(),
                row.unit_id,
                row.updated_at.isoformat(),
                list(row.lease_tenants.order_by("tenant_id").values_list("tenant_id", flat=True)),
            ]
            for row in eligible_leases(request).order_by("pk")
        ],
    }


def review_recharge(cost, *, actor, allocations):
    manager(actor)
    if cost.corrects_id:
        raise ValidationError(
            "Prepare charges from the original expense, including its corrections."
        )
    rows, seen = [], set()
    for item in allocations:
        lease = eligible_leases(cost.request).filter(pk=item["lease"]).first()
        if lease is None or lease.pk in seen:
            raise ValidationError("Choose each eligible current tenancy only once.")
        seen.add(lease.pk)
        if not item["reason"].strip() or not item["due"]:
            raise ValidationError("Enter a due date and reason for every proposed charge.")
        rows.append(
            {
                "lease": lease.pk,
                "amount": str(money(item["amount"])),
                "due": item["due"].isoformat(),
                "reason": item["reason"].strip(),
            }
        )
    if not rows:
        raise ValidationError("Enter at least one proposed charge.")
    data = {
        "actor": actor.pk,
        "cost": cost.pk,
        "batch": str(uuid4()),
        "snapshot": snapshot(cost),
        "rows": rows,
    }
    return signing.dumps(data, salt=SALT, compress=True)


def read_review(token, *, actor, cost):
    manager(actor)
    try:
        data = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature:
        raise ValidationError(
            "This review has expired or changed. Prepare the charges again."
        ) from None
    if data["actor"] != actor.pk or data["cost"] != cost.pk:
        raise PermissionDenied
    return data


@transaction.atomic
def confirm_recharge(cost, *, actor, token):
    from datetime import date

    data = read_review(token, actor=actor, cost=cost)
    request = MaintenanceRequest.objects.select_for_update().get(pk=cost.request_id)
    previous = list(Recharge.objects.filter(cost=cost, batch=data["batch"]))
    if previous:
        return previous
    # Serialize with settlement/occupancy changes and ledger corrections, in stable order.
    list(
        Lease.objects.select_for_update()
        .filter(pk__in=[row["lease"] for row in data["rows"]])
        .order_by("pk")
    )
    list(
        LeaseTenant.objects.select_for_update()
        .filter(lease_id__in=[row["lease"] for row in data["rows"]])
        .order_by("pk")
    )
    from apps.ledger.models import Charge

    list(Charge.objects.select_for_update().filter(maintenance_recharge__cost=cost).order_by("pk"))
    if snapshot(cost) != data["snapshot"]:
        raise ValidationError(
            "The expense, prior charges, or eligible tenancies changed. Review again."
        )
    results = []
    for row in data["rows"]:
        lease = eligible_leases(request).get(pk=row["lease"])
        charge = create_charge(
            lease,
            actor=actor,
            description=f"Repair: {row['reason']}",
            amount=money(row["amount"]),
            due_date=date.fromisoformat(row["due"]),
        )
        results.append(
            Recharge.objects.create(cost=cost, batch=data["batch"], lease=lease, charge=charge)
        )
        record(
            actor=actor,
            action=AuditAction.MAINTENANCE_RECHARGE,
            obj=cost,
            lease=lease,
            summary="Reviewed repair charge posted.",
            charge=charge.pk,
            amount=charge.amount,
        )
    touch(request)
    return results


@transaction.atomic
def remove_attachment(attachment, *, actor, reason):
    if not actor.is_active or not (
        actor.is_superuser or actor.role in (Role.ADMIN, Role.SUPERADMIN)
    ):
        raise PermissionDenied
    if not reason.strip():
        raise ValidationError("Explain why this attachment must be removed.")
    attachment = Attachment.objects.select_for_update().get(pk=attachment.pk)
    if attachment.removed_at:
        return
    attachment.removed_at, attachment.removed_by, attachment.removal_reason = (
        timezone.now(),
        actor,
        reason.strip(),
    )
    attachment.save()
    record(
        actor=actor,
        action=AuditAction.MAINTENANCE_FILE_REMOVED,
        obj=attachment,
        summary="Maintenance attachment removed.",
        reason=reason,
        filename=attachment.original_name,
    )
    transaction.on_commit(lambda: attachment.file.delete(save=False))
