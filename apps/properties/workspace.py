"""Read-only workspace projections and validated, addressable navigation preferences."""

from urllib.parse import urlencode

from django.db.models import Prefetch, Q
from django.urls import reverse

from apps.documents.models import Document
from apps.leases.models import Lease
from apps.maintenance.models import MaintenanceRequest
from apps.properties.models import Property, Unit
from apps.responsibilities.services import property_overview

SECTIONS = ("overview", "details", "maintenance", "recoveries", "documents")


def navigation_properties():
    leases = Lease.objects.current().prefetch_related("lease_tenants__tenant")
    units = Unit.objects.prefetch_related(
        Prefetch("leases", queryset=leases, to_attr="workspace_leases"), "amenities"
    ).order_by("identifier")
    return Property.objects.prefetch_related(Prefetch("units", queryset=units))


def workspace_context(request, *, property=None, unit=None, properties=None):
    location = unit.property if unit else property
    rows = list(properties if properties is not None else navigation_properties())
    # Preserve expansion outside the current filtered/paginated results too.
    valid = {str(pk) for pk in Property.objects.values_list("pk", flat=True)}
    key = f"properties-expanded:{request.user.pk}"
    explicit = "open" in request.GET
    raw = request.GET.get("open", "") if explicit else request.session.get(key, "")
    opened = set(str(raw).split(",")[:200]) & valid
    if location and not explicit:
        opened.add(str(location.pk))
    request.session[key] = ",".join(sorted(opened))
    section = request.GET.get("section", "overview")
    if section not in SECTIONS:
        section = "overview"
    state = {k: request.GET[k] for k in ("q", "status", "page", "property") if k in request.GET}

    def url(route, pk=None, *, open_ids=None, local="overview"):
        params = {**state, "open": ",".join(sorted(opened if open_ids is None else open_ids))}
        if local != "overview":
            params["section"] = local
        return reverse(route, args=[pk] if pk is not None else []) + "?" + urlencode(params)

    for p in rows:
        pid = str(p.pk)
        p.workspace_open = pid in opened
        p.workspace_url = url("portfolio:property-detail", p.pk, open_ids=opened | {pid})
        p.toggle_url = (
            url(
                request.resolver_match.view_name,
                request.resolver_match.kwargs.get("pk"),
                open_ids=opened ^ {pid},
                local=section,
            )
            + f"#property-{p.pk}"
        )
        p.workspace_units = list(p.units.all())
        p.workspace_occupied = 0
        for u in p.workspace_units:
            current = u.workspace_leases[0] if u.workspace_leases else None
            u.__dict__["current_lease"] = current
            p.workspace_occupied += bool(u.is_active and current)
            u.workspace_url = url("portfolio:unit-detail", u.pk, open_ids=opened | {pid})
    result = {
        "workspace_properties": rows,
        "workspace_unit_urls": {u.pk: u.workspace_url for p in rows for u in p.workspace_units},
        "workspace_section": section,
        "workspace_location": location,
    }
    if location:
        route = "portfolio:unit-detail" if unit else "portfolio:property-detail"
        pk = unit.pk if unit else location.pk
        result["workspace_tabs"] = [
            {"label": label, "url": url(route, pk, local=value), "active": section == value}
            for value, label in zip(
                SECTIONS,
                ("Overview", "Details", "Maintenance", "Expense recoveries", "Documents"),
                strict=True,
            )
        ]
        if section == "maintenance":
            requests = MaintenanceRequest.objects.visible_to(request.user).filter(property=location)
            result["workspace_requests"] = requests.filter(unit=unit) if unit else requests
        if section == "documents":
            documents = (
                Document.objects.for_staff()
                .filter(Q(property=location) | Q(lease__unit__property=location))
                .distinct()
            )
            result["workspace_documents"] = (
                documents.filter(lease__unit=unit) if unit else documents
            )
        if section == "recoveries":
            recoveries = property_overview(location)
            if unit:
                for row in recoveries:
                    row.shares = [share for share in row.shares if share.unit.pk == unit.pk]
            result["workspace_recoveries"] = recoveries
    return result
