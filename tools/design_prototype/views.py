"""Fixture-backed views. Only the existing pure Decimal calculator is called."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django import forms
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.responsibilities.services import allocate_monthly

from .data import dataset

NOTICE = "Prototype only—no RHP records changed."
ROOT = Path(__file__).resolve().parent
AREAS = {
    "dashboard",
    "properties",
    "units",
    "tenants",
    "leases",
    "ledger",
    "recoveries",
    "maintenance",
    "documents",
    "tenant",
    "preview",
}
NAV = [
    ("dashboard", "Dashboard"),
    ("properties", "Properties"),
    ("tenants", "Tenants"),
    ("leases", "Leases"),
    ("ledger", "Rent & Payments"),
    ("recoveries", "Expense recoveries"),
    ("maintenance", "Maintenance"),
    ("documents", "Documents"),
]


class IsolationHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        response["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response


def find(rows, pk):
    return next((row for row in rows if row["id"] == pk), None)


def csrf_failure(request, reason=""):
    c = context(request, "preview")
    c.update(
        preview_action="Reload this preview form",
        back=request.path,
        error="Form verification failed. Reload the page and try again. " + reason,
    )
    return render(request, "page.html", c, status=403)


def back_path(value, default):
    value = value or ""
    parsed = urlsplit(value or "")
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or "\\" in value:
        return default
    if parsed.path.split("/")[1] not in AREAS:
        return default
    return value


def location_url(path, opened, **params):
    """Keep explicit tree state in links, including plain-form and history navigation."""
    parts = urlsplit(path)
    query = dict(parse_qsl(parts.query))
    query.pop("expanded", None)  # Accept older links, but emit the unified state format.
    query.update(params)
    query["open"] = ",".join(opened)
    return urlunsplit(("", "", parts.path, urlencode(query), parts.fragment))


def property_navigation(request, c):
    known = {str(p["id"]) for p in c["properties"]}
    explicit = "open" in request.GET or "expanded" in request.GET
    if explicit:
        raw = request.GET.get("open", request.GET.get("expanded", ""))[:2000].split(",")
    else:
        raw = request.session.get("property_open", [])
        if "property_open" not in request.session and c["property"]:
            raw = [str(c["property"]["id"])]
    opened = sorted(set(raw) & known)
    if request.session.get("property_open") != opened:
        request.session["property_open"] = opened
    c["open_value"] = ",".join(opened)
    c["opened_properties"] = opened
    c["return_to"] = location_url(request.get_full_path(), opened)
    if urlsplit(c["back"]).path.split("/")[1] in {"properties", "units"}:
        c["back"] = location_url(c["back"], opened)
    selection_back = request.get_full_path() if not c["property"] else c["back"]
    for p in c["properties"]:
        key = str(p["id"])
        p["is_open"] = key in opened
        # Selecting a property opens its units, without collapsing any other property.
        p["workspace_url"] = location_url(
            f"/properties/{p['id']}/", sorted(set(opened) | {key}), back=selection_back
        )
        toggled = sorted(set(opened) ^ {key})
        p["toggle_url"] = location_url(request.get_full_path(), toggled)
        p["workspace_section_urls"] = [
            {
                "label": label,
                "url": location_url(
                    f"/properties/{p['id']}/", opened, section=key_, back=c["back"]
                ),
            }
            for key_, label in (
                ("maintenance", "Maintenance"),
                ("recoveries", "Expense recoveries"),
                ("documents", "Documents"),
            )
        ]
        for u in p["units"]:
            u["workspace_url"] = location_url(f"/units/{u['id']}/", opened, back=selection_back)
    c["all_properties_url"] = location_url("/properties/", opened)
    c["all_units_url"] = location_url("/units/", opened)


def context(request, area):
    data = dataset()
    for t in data["tickets"]:
        t.update(request.session.get("work", {}).get(str(t["id"]), {}))
        t["tone"] = (
            "followup"
            if t["followup"]
            else "done"
            if t["status"] in {"Completed", "Closed"}
            else "urgent"
            if t["priority"] == "Urgent"
            else "high"
            if t["priority"] == "High"
            else "normal"
            if t["priority"] == "Normal"
            else "low"
        )
        unit = find(data["units"], t["unit"])
        property_name = (find(data["properties"], t["property"]) or {}).get(
            "name", "Unassigned property"
        )
        t["location"] = (
            f"{unit['property_obj']['name']} / {unit['name']}"
            if unit
            else f"{property_name} / Common area · synthetic scenario"
        )
    active = [
        t for t in data["tickets"] if t["status"] not in {"Completed", "Closed"} or t["followup"]
    ]
    data["tickets"].sort(
        key=lambda t: (
            0 if t["followup"] else 1,
            {"Urgent": 0, "High": 1, "Normal": 2, "Low": 3}[t["priority"]],
            -int(t["age"].split()[0]),
        )
    )
    active = [t for t in data["tickets"] if t in active]
    data.update(
        {
            "nav": NAV,
            "area": area,
            "title": dict(NAV).get(area, area.title()),
            "active_tickets": active,
            "is_tenant": area == "tenant",
            "return_to": request.get_full_path(),
            "notice": "",
            "error": "",
            "q": request.GET.get("q", "").strip(),
            "status_filter": request.GET.get("status", "active"),
        }
    )
    for key in ("due", "past", "balance"):
        data["total_" + key] = (
            f"{sum((Decimal(x[key]) for x in data['leases']), Decimal('0')):,.2f}"
        )
    data["occupied_count"] = sum(u["occupied"] for u in data["units"])
    return data


@require_GET
def asset(request, name):
    types = {
        "prototype.css": "text/css",
        "prototype.js": "text/javascript",
        **{f"{key}.png": "image/png" for key in ("alder", "cedar", "studio", "portrait")},
    }
    if name not in types or not (ROOT / "static" / name).is_file():
        raise Http404
    return FileResponse(
        (ROOT / "static" / name).open("rb"),
        content_type=types[name],
    )


@require_POST
def reset(request):
    request.session.flush()
    return redirect("/?reset=1")


@require_http_methods(["GET", "POST"])
def page(request, area="dashboard", pk=None):
    if area not in AREAS:
        raise Http404
    c = context(request, area)
    if request.method == "POST" and (area != "maintenance" or pk is None):
        return HttpResponseBadRequest("Only simulated maintenance updates are available here.")
    c["back"] = back_path(
        request.GET.get("back", ""),
        "/properties/" if area in {"properties", "units"} and pk else f"/{area}/",
    )
    c["q"] = request.GET.get("q", "").strip()
    c["property_filter"] = request.GET.get("property", "")
    c["status_filter"] = request.GET.get("status", "active")
    if area in {"properties", "units"}:
        c["property"] = find(c["properties"], pk) if area == "properties" else None
        c["unit"] = find(c["units"], pk) if area == "units" else None
        if pk is not None and not (c["property"] or c["unit"]):
            raise Http404
        if c["unit"]:
            c["property"] = c["unit"]["property_obj"]
        c["property_nav"] = (
            "units"
            if (area == "units" and (not pk or c["back"].startswith("/units/")))
            else "properties"
        )
        if c["property"]:
            c["title"] = "Properties"
        c["rows"] = [p for p in c["properties"] if c["q"].lower() in p["name"].lower()]
        c["unit_rows"] = [
            u
            for u in c["units"]
            if (not c["property_filter"] or str(u["property"]) == c["property_filter"])
            and c["q"].lower() in u["name"].lower()
        ]
        property_navigation(request, c)
        sections = [
            ("overview", "Overview"),
            ("details", "Details"),
            ("maintenance", "Maintenance"),
            ("recoveries", "Expense recoveries"),
            ("documents", "Documents"),
        ]
        c["section"] = request.GET.get("section", "overview")
        if c["section"] not in dict(sections):
            raise Http404
        c["local_sections"] = [
            {
                "key": key,
                "label": label,
                "url": location_url(
                    request.path, c["opened_properties"], section=key, back=c["back"]
                ),
            }
            for key, label in sections
        ]
        if c["property"]:
            property_id = c["property"]["id"]
            unit_id = c["unit"]["id"] if c["unit"] else None
            c["scoped_tickets"] = [
                t
                for t in c["tickets"]
                if t["property"] == property_id and (not unit_id or t["unit"] == unit_id)
            ]
            # Bills belong to a property; unit views include only bills allocating to that unit.
            c["scoped_bills"] = [
                b
                for b in c["bills"]
                if b["property"] == property_id and (not unit_id or str(unit_id) in b["amounts"])
            ]
            c["scoped_documents"] = [
                d
                for d in c["documents"]
                if d["property"] == property_id and (not unit_id or d.get("unit") == unit_id)
            ]
    elif area in {"tenants", "leases", "ledger"}:
        c["person"] = find(c["tenants"], pk) if area == "tenants" else None
        c["lease"] = find(c["leases"], pk) if area in {"leases", "ledger"} else None
        if pk is not None and not (c["person"] or c["lease"]):
            raise Http404
        c["rows"] = [
            item
            for item in c["leases"]
            if (not c["person"] or c["person"]["id"] in item["tenants"])
            and c["q"].lower() in (item["tenant_names"] + item["unit_obj"]["name"]).lower()
        ]
        c["people_rows"] = [t for t in c["tenants"] if c["q"].lower() in t["name"].lower()]
    elif area == "maintenance":
        c["work_statuses"] = [
            "Open",
            "Acknowledged",
            "Scheduled",
            "In progress",
            "Waiting",
            "Completed",
            "Closed",
        ]
        c["ticket"] = find(c["tickets"], pk)
        if pk is not None and not c["ticket"]:
            raise Http404
        if request.method == "POST":
            target = request.POST.get("status", "")
            statuses = [
                "Open",
                "Acknowledged",
                "Scheduled",
                "In progress",
                "Waiting",
                "Completed",
                "Closed",
            ]
            if target not in statuses:
                c["error"] = "Choose a valid work status."
            elif (
                statuses.index(target) < statuses.index(c["ticket"]["status"])
                and not request.POST.get("reason", "").strip()
            ):
                c["error"] = "Give a reason for moving work backward."
            elif target == "Scheduled" and not request.POST.get("scheduled", "").strip():
                c["error"] = "Enter a date or time window for scheduled work."
            else:
                work = request.session.get("work", {})
                work[str(pk)] = {
                    "status": target,
                    "followup": c["ticket"]["followup"],
                    "reason": request.POST.get("reason", "").strip(),
                    "scheduled": request.POST.get("scheduled", "").strip(),
                }
                request.session["work"] = work
                c = context(request, area)
                c["ticket"] = find(c["tickets"], pk)
                c["notice"] = NOTICE
                c["back"] = back_path(request.GET.get("back", ""), "/maintenance/")
                c["work_statuses"] = [
                    "Open",
                    "Acknowledged",
                    "Scheduled",
                    "In progress",
                    "Waiting",
                    "Completed",
                    "Closed",
                ]
        c["rows"] = [
            t
            for t in c["tickets"]
            if (c["status_filter"] == "all" or t in c["active_tickets"])
            and c["q"].lower() in (t["title"] + t["location"]).lower()
        ]
    elif area == "recoveries":
        c["rows"] = [
            b
            for b in c["bills"]
            if not c["property_filter"] or str(b["property"]) == c["property_filter"]
        ]
        for bill in c["rows"]:
            bill["property_obj"] = find(c["properties"], bill["property"])
    elif area == "tenant":
        # The tenant sample contains no other tenancy's financial projection or staff notes.
        c["lease"] = next((item for item in c["leases"] if item["status"] == "ACTIVE"), None)
        c["tenant_tickets"] = [
            t for t in c["active_tickets"] if c["lease"] and t["unit"] == c["lease"]["unit"]
        ]
        c["tenants"] = []
        c["leases"] = []
        c["tickets"] = []
    elif area == "documents":
        c["document_rows"] = [
            d
            for d in c["documents"]
            if not c["property_filter"] or str(d["property"]) == c["property_filter"]
        ]
    if area == "preview":
        c["preview_action"] = request.GET.get("action", "Action preview")[:120]
    return render(request, "page.html", c)


class AllocationForm(forms.Form):
    remainder = forms.ChoiceField(label="Send the remaining monthly amount to…")
    method = forms.ChoiceField(
        choices=[("custom", "Custom amounts"), ("size", "Size based"), ("equal", "Equal shares")]
    )

    def __init__(self, units, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["remainder"].choices = [("rhp", "RHP — leave unallocated money with RHP")] + [
            (str(u["id"]), u["name"]) for u in units
        ]
        self.fields["remainder"].widget.attrs["aria-label"] = (
            "Send the remaining monthly amount to…"
        )
        for u in units:
            for suffix, label in (("amount", "Monthly dollars"), ("percent", "Percentage")):
                self.fields[f"{suffix}_{u['id']}"] = forms.DecimalField(
                    label=f"{u['name']}: {label}",
                    required=False,
                    min_value=0,
                    max_value=Decimal("999999999.99") if suffix == "amount" else 100,
                    decimal_places=2,
                    max_digits=14,
                )
                self.fields[f"{suffix}_{u['id']}"].widget.attrs["aria-label"] = (
                    f"{u['name']}: {label}"
                )
                if str(u["id"]) == self.data.get("remainder"):
                    self.fields[f"{suffix}_{u['id']}"].widget.attrs["readonly"] = True
            self.fields[f"basis_{u['id']}"] = forms.ChoiceField(
                choices=[
                    ("amount", "Monthly dollars"),
                    ("percent", "Percentage"),
                    ("excluded", "Exclude from this bill"),
                ]
            )


def worksheet_context(request, pk):
    c = context(request, "recoveries")
    bill = find(c["bills"], pk)
    if not bill:
        raise Http404
    units = [u for u in c["units"] if u["property"] == bill["property"]]
    scenario = request.POST.get("scenario", request.GET.get("scenario", "saved"))
    # Alternate states are deliberately synthetic, not changes to the snapshot.
    if scenario == "zero":
        bill.update(total="0.00", monthly="0.00", amounts={})
    if scenario == "locked":
        bill["locked"] = True
    if scenario == "missing-size" and units:
        units[0]["size"] = None
    if scenario == "vacant" and units:
        units[-1]["occupied"] = False
    initial = {"method": "custom", "remainder": "rhp"}
    for u in units:
        initial.update(
            {
                f"amount_{u['id']}": bill["amounts"].get(str(u["id"]), "0.00"),
                f"percent_{u['id']}": "0.00",
                f"basis_{u['id']}": "amount",
            }
        )
    saved = request.session.get("drafts", {}).get(f"{pk}:{scenario}", initial)
    payload = request.POST if request.method == "POST" else saved
    form = AllocationForm(units, payload)
    worksheet = None
    if form.is_valid():
        try:
            bases = {u["id"]: form.cleaned_data[f"basis_{u['id']}"] for u in units}
            amounts = {
                u["id"]: form.cleaned_data[f"amount_{u['id']}"] or Decimal("0") for u in units
            }
            percentages = {
                u["id"]: form.cleaned_data[f"percent_{u['id']}"] or Decimal("0") for u in units
            }
            for u in units:
                key = f"{bases[u['id']]}_{u['id']}"
                if (
                    bases[u["id"]] != "excluded"
                    and str(u["id"]) != form.cleaned_data["remainder"]
                    and form.cleaned_data.get(key) is None
                ):
                    raise ValidationError(f"Enter the controlling value for {u['name']}.")
            worksheet = allocate_monthly(
                SimpleNamespace(monthly_total=Decimal(bill["monthly"])),
                units=[SimpleNamespace(pk=u["id"], square_feet=u["size"]) for u in units],
                amounts=amounts,
                percentages=percentages,
                bases=bases,
                remainder=form.cleaned_data["remainder"],
                method=form.cleaned_data["method"],
            )
            paired = form.data.copy()
            for line in worksheet.rows:
                if (
                    bases[line.unit.pk] != "amount"
                    or form.cleaned_data["method"] != "custom"
                    or str(line.unit.pk) == form.cleaned_data["remainder"]
                ):
                    paired[f"amount_{line.unit.pk}"] = str(line.amount)
                if (
                    bases[line.unit.pk] != "percent"
                    or form.cleaned_data["method"] != "custom"
                    or str(line.unit.pk) == form.cleaned_data["remainder"]
                ):
                    paired[f"percent_{line.unit.pk}"] = str(line.percent)
            form.data = paired
        except (ValidationError, InvalidOperation) as exc:
            form.add_error(None, str(exc))
    rows, offset = [], Decimal("0")
    rhp = worksheet.left if worksheet else Decimal("0")
    for u in units:
        line = (
            next((r for r in worksheet.rows if r.unit.pk == u["id"]), None) if worksheet else None
        )
        row = {
            "unit": u,
            "amount_field": form[f"amount_{u['id']}"],
            "percent_field": form[f"percent_{u['id']}"],
            "basis_field": form[f"basis_{u['id']}"],
            "saved": bill["amounts"].get(str(u["id"]), "0.00"),
            "line": line,
            "offset": -offset,
        }
        if line:
            row["change"] = line.amount - Decimal(row["saved"])
            row["geometry"] = (line.amount / worksheet.cap * 100) if worksheet.cap else Decimal("0")
            offset += row["geometry"]
            if not u["occupied"]:
                rhp += line.amount
        rows.append(row)
    c.update(
        bill=bill,
        property=find(c["properties"], bill["property"]),
        form=form,
        rows=rows,
        worksheet=worksheet,
        rhp=rhp,
        remainder_offset=-offset,
        scenario=scenario,
        step="allocate",
        back=back_path(request.GET.get("back"), f"/recoveries/?property={bill['property']}"),
    )
    c["rounding"] = (
        worksheet.cap * bill["months"] - Decimal(bill["total"]) if worksheet else Decimal("0")
    )
    c["valid"] = worksheet is not None and not form.errors and not worksheet.over
    return c


@require_http_methods(["GET", "POST"])
def allocation(request, pk):
    c = worksheet_context(request, pk)
    action = request.POST.get("action", "calculate")
    if request.method == "POST" and not c["bill"]["locked"]:
        if c["form"].is_valid():
            drafts = request.session.get("drafts", {})
            drafts[f"{pk}:{c['scenario']}"] = {
                k: v for k, v in request.POST.items() if k not in {"csrfmiddlewaretoken", "action"}
            }
            request.session["drafts"] = drafts
        if action in {"review", "save"} and c["valid"]:
            signature = hashlib.sha256(
                json.dumps(
                    {
                        "bill": c["bill"],
                        "rows": [(r["unit"]["id"], str(r["line"].amount)) for r in c["rows"]],
                        "remainder": c["form"].cleaned_data["remainder"],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            if action == "review":
                request.session["review"] = signature
                c["step"] = "review"
            elif request.session.pop("review", None) == signature:
                c["step"] = "complete"
                c["notice"] = NOTICE
            else:
                c["error"] = (
                    "Allocation changed or review expired. Review it again before confirming."
                )
    return render(request, "allocation.html", c)


@require_POST
def allocation_preview(request, pk):
    c = worksheet_context(request, pk)
    if c["bill"]["locked"]:
        return JsonResponse(
            {"error": "This bill is locked; no allocations can be changed."}, status=409
        )
    from django.template.loader import render_to_string

    return JsonResponse(
        {
            "summary": render_to_string("ring.html", c, request=request),
            "values": [
                {
                    "id": r["unit"]["id"],
                    "amount": str(r["line"].amount),
                    "percent": str(r["line"].percent),
                }
                for r in c["rows"]
                if r["line"]
            ],
            "errors": c["form"].errors.get_json_data(),
            "valid": c["valid"],
        }
    )
