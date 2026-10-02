"""Recording audit events.

One function, called inside the transaction that makes the change, so an event can
never survive a rolled-back write or go missing from a committed one.
"""

import datetime as dt
from decimal import Decimal

from apps.audit.models import AuditEvent


def _jsonable(value):
    """Coerce the small set of values an event carries into JSON-safe ones.

    Money is rendered as a string rather than a float: the ledger's rule about
    ``Decimal`` does not stop at the audit table (docs/database.md).
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(
    actor, action: str, *, obj=None, lease=None, summary: str = "", **metadata
) -> AuditEvent:
    """Append one event for ``obj``.

    ``actor`` may be ``None`` or an anonymous user (a scheduled command); the
    event still records that the change happened.
    """
    if not getattr(actor, "is_authenticated", False):
        actor = None

    if obj is not None and lease is None:
        lease = getattr(obj, "lease", None)

    return AuditEvent.objects.create(
        actor=actor,
        lease=lease,
        action=action,
        object_type=(f"{obj._meta.app_label}.{obj.__class__.__name__}" if obj is not None else ""),
        object_id=getattr(obj, "pk", None),
        summary=(summary or (str(obj) if obj is not None else ""))[:255],
        metadata={key: _jsonable(value) for key, value in metadata.items()},
    )


def events_for_lease(lease, *, limit: int | None = None):
    """The history of one tenancy, newest first."""
    events = AuditEvent.objects.for_lease(lease).select_related("actor")
    return events[:limit] if limit else events
