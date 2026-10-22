"""Reviewed recovery of a missing billing start date; never rewrites financial entries."""

import datetime as dt
import hashlib
import json

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import MANAGER_ROLES
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.leases.models import Lease, LeaseAccountStatus
from apps.ledger.services import build_ledger

SALT = "lease-existing-history-review"
STALE = "This account changed or the review expired. Review the existing history again."


def _authorize(actor):
    if not (
        actor.is_authenticated
        and actor.is_active
        and (actor.is_superuser or actor.role in MANAGER_ROLES)
    ):
        raise PermissionDenied


def _snapshot(lease):
    if (
        not lease.needs_starting_account
        or lease.account_status != LeaseAccountStatus.OPEN
        or not (lease.charges.exists() or lease.payments.exists())
    ):
        raise ValidationError("This lease is not eligible to confirm existing account history.")
    data = {
        "lease": [
            lease.pk,
            lease.unit_id,
            lease.status,
            lease.account_status,
            lease.start_date,
            lease.end_date,
            lease.billing_start_date,
            lease.updated_at,
        ],
        "charges": list(lease.charges.order_by("pk").values()),
        "payments": list(lease.payments.order_by("pk").values()),
        "rent": list(lease.rent_periods.order_by("pk").values()),
        "nnn": list(lease.nnn_rates.order_by("pk").values()),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def prepare(lease, *, billing_start_date, reason, actor):
    _authorize(actor)
    # Refetch: prefetched/cached instances must not authorize a stale review.
    lease = Lease.objects.select_related("unit__property").get(pk=lease.pk)
    fingerprint = _snapshot(lease)
    if not lease.start_date <= billing_start_date <= lease.end_date:
        raise ValidationError("The billing start date must fall within the lease dates.")
    reason = reason.strip()
    if not reason or len(reason) > 200:
        raise ValidationError("Enter a reason of no more than 200 characters.")
    ledger = build_ledger(lease)
    dates = [line.charge.due_date for line in ledger.charges]
    dates += [payment.payment_date for payment in ledger.payments]
    payload = {
        "lease": lease.pk,
        "actor": actor.pk,
        "date": billing_start_date.isoformat(),
        "reason": reason,
        "fingerprint": fingerprint,
    }
    return {
        "token": signing.dumps(payload, salt=SALT),
        "billing_start_date": billing_start_date,
        "reason": reason,
        "charge_count": len(ledger.charges),
        "payment_count": len(ledger.payments),
        "earliest": min(dates),
        "latest": max(dates),
        "balance": ledger.balance_due,
    }


@transaction.atomic
def confirm(lease_id, *, token, actor):
    _authorize(actor)
    try:
        payload = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError(STALE) from exc
    if payload.get("actor") != actor.pk or payload.get("lease") != lease_id:
        raise ValidationError(STALE)
    lease = Lease.objects.select_for_update().get(pk=lease_id)
    if payload.get("fingerprint") != _snapshot(lease):
        raise ValidationError(STALE)
    date = dt.date.fromisoformat(payload["date"])
    if not lease.start_date <= date <= lease.end_date:
        raise ValidationError(STALE)
    lease.billing_start_date = date
    lease.save(update_fields=["billing_start_date", "updated_at"])
    record(
        actor,
        AuditAction.LEASE_ONBOARDED,
        obj=lease,
        lease=lease,
        summary="Billing start date confirmed; existing account history kept",
        workflow="keep_existing_history",
        billing_start_date=date,
        reason=payload["reason"],
        reviewed_fingerprint=payload["fingerprint"],
    )
    return lease
