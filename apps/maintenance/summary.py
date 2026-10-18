from django.db.models import Q
from django.urls import reverse

from .models import Audience, MaintenanceRequest, Status


def maintenance_summary(user, *, property=None, unit=None):
    rows = MaintenanceRequest.objects.visible_to(user)
    flagged = Audience.objects.filter(unresolved=True)
    if user.is_tenant:
        flagged = flagged.filter(lease__lease_tenants__tenant=user)
    rows = rows.filter(
        ~Q(status__in=[Status.COMPLETED, Status.CLOSED]) | Q(pk__in=flagged.values("request_id"))
    )
    query = ""
    if property:
        rows = rows.filter(property=property)
        query = f"?property={property.pk}"
    if unit:
        rows = rows.filter(unit=unit)
        query = f"?unit={unit.pk}"
    namespace = "tenant_maintenance" if user.is_tenant else "maintenance"
    return {
        "count": rows.count(),
        "follow_up": rows.filter(pk__in=flagged.values("request_id")).count(),
        "url": reverse(f"{namespace}:list") + query,
    }
