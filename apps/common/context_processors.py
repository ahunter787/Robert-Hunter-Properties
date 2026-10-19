"""Role-aware navigation; never a substitute for endpoint authorization."""

from django.urls import reverse


def portal_navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {"portal_shell": False}
    match = request.resolver_match
    namespace = match.namespace if match else ""
    name = match.url_name if match else ""
    active = {
        "portfolio": "properties",
        "leases": "leases",
        "ledger": "ledger",
        "responsibilities": "recoveries",
        "maintenance": "maintenance",
        "documents": "documents",
        "tenancy": "lease",
        "payments": "payments",
        "tenant_documents": "documents",
        "tenant_maintenance": "maintenance",
    }.get(namespace, "dashboard")
    if namespace == "manage" and name.startswith("account-"):
        active = "tenants"
    if namespace == "accounts" and name not in ("home", "login"):
        active = "profile"
    if user.is_manager_or_above:
        items = [
            ("dashboard", "Dashboard", "manage:home"),
            ("properties", "Properties", "portfolio:property-list"),
            ("tenants", "Tenants", "manage:account-list"),
            ("leases", "Leases", "leases:lease-list"),
            ("ledger", "Rent & Payments", "ledger:overview"),
            ("recoveries", "Expense recoveries", "responsibilities:overview"),
            ("maintenance", "Maintenance", "maintenance:list"),
            ("documents", "Documents", "documents:list"),
        ]
    elif user.is_tenant:
        items = [
            ("dashboard", "Dashboard", "accounts:home"),
            ("lease", "Lease", "tenancy:lease"),
            ("payments", "Payments", "payments:home"),
            ("maintenance", "Maintenance", "tenant_maintenance:list"),
            ("documents", "Documents", "tenant_documents:list"),
        ]
    else:
        items = [("maintenance", "Assigned work", "maintenance:list")]
    return {
        "portal_shell": True,
        "portal_active": active,
        "portal_nav": [
            {"key": key, "label": label, "url": reverse(route), "active": key == active}
            for key, label, route in items
        ],
        "portfolio_units_active": namespace == "portfolio" and name.startswith("unit-"),
    }
