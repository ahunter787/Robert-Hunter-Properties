"""One-time export: allowlisted fields only, in a database-enforced read-only transaction."""

import json
import os
import tempfile
from pathlib import Path

from django.db import connection, transaction
from django.utils import timezone


def snapshot_data():
    from apps.accounts.models import Role, User
    from apps.leases.models import Lease
    from apps.ledger.services import build_ledger
    from apps.properties.models import Property, Unit
    from apps.responsibilities.models import ResponsibilityCycle
    from apps.responsibilities.services import cycle_is_locked

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        result = {
            "schema": 1,
            "source": "Private local RHP snapshot — partially verified development data",
            "properties": [
                {
                    "id": p.pk,
                    "name": p.name,
                    "address": p.address_line,
                    "type": p.get_property_type_display(),
                }
                for p in Property.objects.order_by("pk")
            ],
            "units": [
                {"id": u.pk, "property": u.property_id, "name": u.identifier, "size": u.square_feet}
                for u in Unit.objects.order_by("pk")
            ],
            "tenants": [
                {"id": t.pk, "name": t.display_name}
                for t in User.objects.filter(role=Role.TENANT).order_by("pk")
            ],
            "leases": [],
            "bills": [],
            "documents": [],
        }
        for lease in (
            Lease.objects.select_related("unit__property")
            .prefetch_related("lease_tenants__tenant")
            .order_by("pk")
        ):
            ledger = build_ledger(lease)
            end = lease.end_date.strftime("%b %-d, %Y") if lease.end_date else "Ongoing"
            next_charge = ledger.next_charge
            result["leases"].append(
                {
                    "id": lease.pk,
                    "unit": lease.unit_id,
                    "tenants": list(lease.lease_tenants.values_list("tenant_id", flat=True)),
                    "status": lease.status,
                    "current": lease.is_current,
                    "account": lease.account_status,
                    "rent": str(lease.current_month_total),
                    "due": str(ledger.due_now),
                    "past": str(ledger.arrears),
                    "upcoming": str(ledger.not_yet_due),
                    "balance": str(ledger.balance_due),
                    "template": lease.get_template_display(),
                    "dates": f"{lease.start_date.strftime('%b %-d, %Y')} – {end}",
                    "next_date": next_charge.date.strftime("%b %-d, %Y")
                    if next_charge
                    else "No posted upcoming charge",
                    "pending": bool(ledger.pending_payments),
                    "transactions": [],
                }
            )
        for cycle in (
            ResponsibilityCycle.objects.select_related("responsibility")
            .prefetch_related("shares")
            .order_by("pk")
        ):
            result["bills"].append(
                {
                    "id": cycle.pk,
                    "property": cycle.responsibility.property_id,
                    "name": cycle.responsibility.label,
                    "total": str(cycle.total_amount),
                    "months": cycle.months,
                    "monthly": str(cycle.monthly_total),
                    "period": (
                        f"{cycle.starts_on.strftime('%b %-d, %Y')} – "
                        f"{cycle.ends_on.strftime('%b %-d, %Y')}"
                    ),
                    "locked": cycle_is_locked(cycle),
                    "amounts": {str(s.unit_id): str(s.monthly_amount) for s in cycle.shares.all()},
                }
            )
        result["source"] += " · " + timezone.localdate().isoformat()
        return result


def export_snapshot():
    # Build the complete projection before creating any file. No uploads or message bodies are read.
    content = json.dumps(snapshot_data(), ensure_ascii=False)
    directory = Path(tempfile.mkdtemp(prefix="rhp-design-private-"))
    target = directory / "snapshot.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    return target
