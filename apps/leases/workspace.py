"""Read-only navigation for a lease; URL state never grants access."""

from urllib.parse import urlencode

from django.urls import reverse

SECTIONS = (
    ("ledger", "Rent & Payments"),
    ("terms", "Terms"),
    ("rent", "Rent schedule"),
    ("tenants", "Tenants"),
    ("documents", "Documents"),
)


def workspace_context(request, lease):
    section = request.GET.get("section", "ledger")
    if section not in dict(SECTIONS):
        section = "ledger"
    # Carry only bounded, recognized list filters. Never accept a return URL.
    filters = {}
    for key in ("q", "status", "expiring", "page"):
        value = request.GET.get(key, "")[:200]
        if value:
            filters[key] = value
    base = reverse("leases:lease-detail", args=[lease.pk])
    return {
        "lease_section": section,
        "lease_tabs": [
            {
                "label": label,
                "active": section == key,
                "url": base + "?" + urlencode({**filters, "section": key}),
            }
            for key, label in SECTIONS
        ],
    }
