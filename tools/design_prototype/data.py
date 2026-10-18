"""Synthetic fixtures and a strict, allowlisted private snapshot loader."""

import copy
import json
from pathlib import Path

_snapshot = None
COLORS = ["#2563eb", "#db2777", "#7c3aed", "#0891b2", "#b45309", "#475569"]


def synthetic():
    return {
        "source": "Synthetic review data",
        "properties": [
            {"id": 1, "name": "Alder Court", "address": "100 Example Street", "type": "Commercial"},
            {"id": 2, "name": "Cedar House", "address": "200 Sample Avenue", "type": "Residential"},
        ],
        "units": [
            {"id": 1, "property": 1, "name": "Studio A", "size": 840},
            {"id": 2, "property": 1, "name": "Studio B", "size": 1160},
            {"id": 3, "property": 2, "name": "Apartment 1", "size": 700},
            {"id": 4, "property": 2, "name": "Apartment 2", "size": 700},
            {"id": 5, "property": 2, "name": "Apartment 3", "size": 700},
        ],
        "tenants": [
            {"id": 1, "name": "Alex Morgan"},
            {"id": 2, "name": "Jordan Lee"},
            {"id": 3, "name": "Taylor Reed"},
            {"id": 4, "name": "Casey Ellis"},
        ],
        "leases": [
            lease(1, 1, [1], "ACTIVE", "OPEN", "1200.00", "240.00", "240.00", "840.00", "1080.00"),
            lease(2, 2, [2], "ACTIVE", "OPEN", "1450.00", "0.00", "0.00", "0.00", "-125.00"),
            lease(3, 3, [3], "ACTIVE", "OPEN", "1100.00", "1100.00", "1100.00", "0.00", "1100.00"),
            lease(4, 4, [4], "ENDED", "SETTLED", "1100.00", "0.00", "0.00", "0.00", "0.00"),
        ],
        "bills": [
            {
                "id": 1,
                "property": 1,
                "name": "Electricity",
                "total": "237.00",
                "months": 3,
                "monthly": "79.00",
                "period": "Oct 1 – Dec 31, 2026",
                "locked": False,
                "amounts": {"1": "33.20", "2": "45.80"},
            },
            {
                "id": 2,
                "property": 2,
                "name": "Water",
                "total": "300.00",
                "months": 3,
                "monthly": "100.00",
                "period": "Oct 1 – Dec 31, 2026",
                "locked": False,
                "amounts": {"3": "30.00", "4": "30.00", "5": "30.00"},
            },
        ],
        "documents": [
            {
                "id": 1,
                "property": 1,
                "name": "Studio A — signed lease",
                "unit": 1,
                "category": "Lease",
                "visibility": "Tenant shared",
            },
            {
                "id": 2,
                "property": 2,
                "name": "Cedar House — inspection notes",
                "category": "Inspection",
                "visibility": "Staff only",
            },
        ],
    }


def lease(pk, unit, tenants, status, account, rent, due, past, upcoming, balance):
    return {
        "id": pk,
        "unit": unit,
        "tenants": tenants,
        "status": status,
        "account": account,
        "rent": rent,
        "due": due,
        "past": past,
        "upcoming": upcoming,
        "balance": balance,
        "dates": "Jan 1 – Dec 31, 2026",
        "next_date": "Nov 5, 2026",
        "template": "Fixed",
        "pending": pk == 3,
        "transactions": [
            {
                "date": "Oct 5, 2026",
                "description": "October rent",
                "charge": rent,
                "payment": "—",
                "balance": rent,
                "state": "Posted",
                "correction": "Original $1,250.00 · credited $50.00" if pk == 1 else "",
            },
            {
                "date": "Oct 12, 2026",
                "description": "Payment recorded",
                "charge": "—",
                "payment": "960.00" if pk == 1 else "0.00",
                "balance": due,
                "state": "Pending" if pk == 3 else "Cleared",
                "correction": "",
            },
            {
                "date": "Nov 5, 2026",
                "description": "Upcoming posted charges",
                "charge": upcoming,
                "payment": "—",
                "balance": balance,
                "state": "Not yet due",
                "correction": "",
            },
        ]
        if pk == 1
        else [],
    }


def load_snapshot(path):
    """Accept only the exporter schema; never read a file specified in an HTTP request."""
    global _snapshot
    candidate = Path(path).resolve()
    if candidate.stat().st_size > 5_000_000:
        raise ValueError("Snapshot exceeds the 5 MB prototype limit.")
    value = json.loads(candidate.read_text())
    if value.get("schema") != 1 or set(value) != {
        "schema",
        "source",
        "properties",
        "units",
        "tenants",
        "leases",
        "bills",
        "documents",
    }:
        raise ValueError("Use a snapshot created by the prototype exporter.")
    _snapshot = value


def dataset():
    value = copy.deepcopy(_snapshot if _snapshot is not None else synthetic())
    synthetic_images = _snapshot is None
    for p in value["properties"]:
        p["image"] = (
            f"/assets/{'alder' if p['id'] == 1 else 'cedar'}.png" if synthetic_images else ""
        )
    for u in value["units"]:
        u["image"] = "/assets/studio.png" if synthetic_images and u["id"] <= 2 else ""
    for t in value["tenants"]:
        t["image"] = "/assets/portrait.png" if synthetic_images and t["id"] == 1 else ""
    properties = {p["id"]: p for p in value["properties"]}
    tenants = {t["id"]: t for t in value["tenants"]}
    for u in value["units"]:
        u["property_obj"] = properties[u["property"]]
        siblings = [x for x in value["units"] if x["property"] == u["property"]]
        u["color"] = COLORS[siblings.index(u) % len(COLORS)]
        u["lease"] = next(
            (
                x
                for x in value["leases"]
                if x["unit"] == u["id"] and x.get("current", x["status"] == "ACTIVE")
            ),
            None,
        )
        u["occupied"] = u["lease"] is not None
    units = {u["id"]: u for u in value["units"]}
    for item in value["leases"]:
        item["unit_obj"] = units[item["unit"]]
        item["people"] = [tenants[t] for t in item["tenants"] if t in tenants]
        item["tenant_names"] = ", ".join(t["name"] for t in item["people"])
    for p in value["properties"]:
        p["units"] = [u for u in value["units"] if u["property"] == p["id"]]
        p["occupied"] = sum(u["occupied"] for u in p["units"])
    # Work/conversation content is always synthetic, even with a private portfolio snapshot.
    value["tickets"] = [
        {
            "id": 1,
            "title": "Water beneath kitchen sink",
            "unit": value["units"][0]["id"] if value["units"] else None,
            "priority": "High",
            "status": "Open",
            "age": "2 days",
            "entry": "No",
            "followup": False,
        },
        {
            "id": 2,
            "title": "Hallway light flickering",
            "unit": None,
            "priority": "Normal",
            "status": "Acknowledged",
            "age": "1 day",
            "entry": "No",
            "followup": False,
        },
        {
            "id": 3,
            "title": "Replace cabinet handle",
            "unit": None,
            "priority": "Low",
            "status": "Open",
            "age": "3 days",
            "entry": "No",
            "followup": False,
        },
        {
            "id": 4,
            "title": "Heating repair follow-up",
            "unit": None,
            "priority": "Urgent",
            "status": "Completed",
            "age": "4 days",
            "entry": "No",
            "followup": True,
        },
        {
            "id": 5,
            "title": "Door closer adjusted",
            "unit": None,
            "priority": "Low",
            "status": "Closed",
            "age": "5 days",
            "entry": "No",
            "followup": False,
        },
    ]
    for ticket in value["tickets"]:
        unit = units.get(ticket["unit"])
        property_ids = list(properties)
        ticket["property"] = (
            unit["property"]
            if unit
            else property_ids[min(1 if ticket["id"] >= 4 else 0, len(property_ids) - 1)]
            if property_ids
            else None
        )
    return value
