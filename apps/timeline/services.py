"""One authorized timeline read model; money facts come from the ledger, not recomputed."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.communications.models import Conversation
from apps.documents.models import Document
from apps.maintenance.models import Cost, MaintenanceRequest, Update

from .models import TimelineEntry

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Event:
    occurred_at: dt.datetime
    category: str
    title: str
    detail: str = ""
    actor: str = ""
    visible_to_tenant: bool = True
    key: str = ""
    amount: Decimal | None = None


def _when(value):
    if isinstance(value, dt.datetime):
        return value
    return timezone.make_aware(dt.datetime.combine(value, dt.time.min))


def _amount(value):
    return f"${value:,.2f}" if value is not None else ""


def can_view(lease, viewer):
    if not getattr(viewer, "is_authenticated", False) or not viewer.is_active:
        return False
    if viewer.is_manager_or_above:
        return True
    return lease.lease_tenants.filter(tenant=viewer).exists()


def _lease_events(lease):
    events = [
        Event(
            lease.created_at,
            "lease",
            "Tenancy created",
            f"{lease.unit.label} · {lease.start_date} to {lease.end_date}",
            key=f"lease:{lease.pk}:created",
        )
    ]
    events.append(
        Event(
            _when(lease.start_date),
            "lease",
            (
                "Tenancy started"
                if lease.start_date <= timezone.localdate()
                else "Tenancy scheduled to start"
            ),
            f"{lease.unit.label}",
            key=f"lease:{lease.pk}:start",
        )
    )
    if lease.ended_on:
        events.append(
            Event(
                _when(lease.ended_on),
                "lease",
                "Tenancy ended",
                lease.end_reason_note or lease.get_end_reason_display(),
                key=f"lease:{lease.pk}:ended",
            )
        )
    return events


def _ledger_events(lease):
    events = []
    for charge in lease.charges.select_related("adjusts"):
        if charge.adjusts_id:
            title = "Charge corrected"
            detail = f"{charge.description} · {charge.reason or 'adjustment'}"
        else:
            title = f"{charge.get_kind_display()} charged"
            detail = charge.description
        events.append(
            Event(
                charge.created_at,
                "money",
                title,
                detail,
                (charge.created_by.display_name if charge.created_by else ""),
                key=f"charge:{charge.pk}",
                amount=charge.balance_effect,
            )
        )
    for payment in lease.payments.all():
        title = "Payment reversed" if payment.reverses_id else "Payment recorded"
        events.append(
            Event(
                payment.created_at,
                "money",
                title,
                f"{payment.get_method_display()} · {payment.external_reference}".strip(" ·"),
                (payment.created_by.display_name if payment.created_by else ""),
                key=f"payment:{payment.pk}",
                amount=payment.amount,
            )
        )
    return events


def _maintenance_events(lease, staff):
    events = []
    requests = MaintenanceRequest.objects.filter(reporting_lease=lease).order_by("pk")
    for request in requests:
        events.append(
            Event(
                request.created_at,
                "maintenance",
                f"Maintenance request: {request.title}",
                request.get_status_display(),
                key=f"maintenance:{request.pk}:created",
            )
        )
        for update in Update.objects.filter(request=request).select_related("author"):
            tenant_visible = update.lease_id == lease.pk
            if tenant_visible or staff:
                events.append(
                    Event(
                        update.created_at,
                        "maintenance",
                        "Maintenance update",
                        update.body[:500],
                        update.author.display_name,
                        tenant_visible,
                        f"maintenance-update:{update.pk}",
                    )
                )
    if staff:
        for cost in Cost.objects.filter(request__reporting_lease=lease):
            events.append(
                Event(
                    cost.created_at,
                    "maintenance",
                    "Maintenance cost recorded",
                    f"{cost.description} · {cost.get_direction_display()}",
                    cost.actor.display_name,
                    False,
                    f"maintenance-cost:{cost.pk}",
                    cost.effect,
                )
            )
    return events


def _document_events(lease, staff):
    events = []
    for document in Document.objects.filter(lease=lease):
        if document.tenant_visible or staff:
            events.append(
                Event(
                    document.created_at,
                    "documents",
                    "Document added",
                    document.title,
                    document.uploaded_by.display_name if document.uploaded_by else "",
                    document.tenant_visible,
                    f"document:{document.pk}",
                )
            )
    return events


def _message_events(lease, viewer):
    events = []
    for conversation in Conversation.objects.visible_to(viewer).filter(lease=lease):
        for message in conversation.messages.select_related("author"):
            events.append(
                Event(
                    message.created_at,
                    "messages",
                    f"Message in “{conversation.subject}”",
                    message.body[:500],
                    message.author.display_name,
                    True,
                    f"message:{message.pk}",
                )
            )
    return events


def _manual_events(lease, staff):
    rows = TimelineEntry.objects.filter(lease=lease).select_related("author")
    if not staff:
        rows = rows.filter(visible_to_tenant=True)
    return [
        Event(
            row.occurred_at,
            "manual",
            row.get_kind_display(),
            row.body,
            row.author.display_name,
            row.visible_to_tenant,
            f"manual:{row.pk}",
        )
        for row in rows
    ]


def timeline_for(lease, viewer):
    if not can_view(lease, viewer):
        raise PermissionDenied
    staff = viewer.is_manager_or_above
    events = []
    events += _lease_events(lease)
    events += _ledger_events(lease)
    events += _maintenance_events(lease, staff)
    events += _document_events(lease, staff)
    events += _message_events(lease, viewer)
    events += _manual_events(lease, staff)
    if not staff:
        events = [event for event in events if event.visible_to_tenant]
    return sorted(events, key=lambda event: (event.occurred_at, event.key), reverse=True)


def add_manual_entry(*, lease, actor, kind, body, occurred_at, visible_to_tenant, document=None):
    if not actor.is_manager_or_above:
        raise PermissionDenied
    body = (body or "").strip()
    if not body or len(body) > 10000:
        raise ValueError("Write an entry of up to 10,000 characters.")
    return TimelineEntry.objects.create(
        lease=lease,
        kind=kind,
        body=body,
        occurred_at=occurred_at,
        author=actor,
        visible_to_tenant=bool(visible_to_tenant),
        document=document,
    )
