"""Role-aware navigation; never a substitute for endpoint authorization."""

from django.urls import reverse


def _nav_unread(user):
    """One small, authorized count for the Messages badge."""
    if not (user.is_active and (user.is_tenant or user.is_manager_or_above)):
        return 0
    try:
        from apps.communications.summary import communications_summary

        summary = communications_summary(user)
    except Exception:  # pragma: no cover - a broken optional summary must not break the shell
        return 0
    return summary["unread"] if summary else 0


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
        "communications": "communications",
        "accounting": "accounting",
        "timeline": "timeline",
        "tenant_timeline": "timeline",
        "tenant_insurance": "insurance",
        "insurance": "insurance",
        "tenant_communications": "communications",
    }.get(namespace, "dashboard")
    if namespace == "ledger" and name == "lease-ledger":
        active = "leases"
    if namespace == "manage" and name.startswith("account-"):
        active = "tenants"
    if namespace == "contacts":
        active = "people"
    if namespace == "accounts" and name not in ("home", "login"):
        active = "profile"
    if namespace in ("communications", "tenant_communications") and name == "announcements":
        active = "announcements"

    if user.is_manager_or_above:
        groups = [
            ("", [("dashboard", "Dashboard", "manage:home")]),
            ("Portfolio", [("properties", "Properties", "portfolio:property-list")]),
            (
                "People",
                [
                    ("tenants", "Tenants", "manage:account-list"),
                    ("people", "People", "contacts:person-list"),
                    ("timeline", "Timeline", "timeline:list"),
                    ("insurance", "Insurance", "insurance:staff-list"),
                ],
            ),
            ("Leasing", [("leases", "Leases", "leases:lease-list")]),
            (
                "Money",
                [
                    ("ledger", "Rent & Payments", "ledger:overview"),
                    ("recoveries", "Expense recoveries", "responsibilities:overview"),
                    ("accounting", "Accounting", "accounting:overview"),
                ],
            ),
            ("Work", [("maintenance", "Maintenance", "maintenance:list")]),
            (
                "Communications",
                [
                    ("communications", "Messages", "communications:index"),
                    ("announcements", "Announcements", "communications:announcements"),
                ],
            ),
            ("Workspace", [("documents", "Documents", "documents:list")]),
        ]
    elif user.is_tenant:
        groups = [
            ("", [("dashboard", "Dashboard", "accounts:home")]),
            (
                "Tenancy",
                [
                    ("lease", "Lease", "tenancy:lease"),
                    ("timeline", "Timeline", "tenant_timeline:timeline"),
                    ("insurance", "Insurance", "tenant_insurance:insurance"),
                ],
            ),
            ("Money", [("payments", "Payments", "payments:home")]),
            (
                "Home",
                [
                    ("maintenance", "Maintenance", "tenant_maintenance:list"),
                    ("documents", "Documents", "tenant_documents:list"),
                ],
            ),
            (
                "Inbox",
                [
                    ("communications", "Messages", "tenant_communications:index"),
                    ("announcements", "Announcements", "tenant_communications:announcements"),
                ],
            ),
        ]
    else:
        groups = [("", [("maintenance", "Assigned work", "maintenance:list")])]

    unread = _nav_unread(user)
    portal_groups = []
    portal_nav = []
    for title, rows in groups:
        group_items = []
        for key, label, route in rows:
            item = {
                "key": key,
                "label": label,
                "url": reverse(route),
                "active": key == active,
                "badge": unread if key == "communications" and unread else 0,
                "badge_label": f"{unread} unread message{'s' if unread != 1 else ''}",
            }
            group_items.append(item)
            portal_nav.append(item)
        portal_groups.append({"title": title, "items": group_items})

    return {
        "portal_shell": True,
        "portal_active": active,
        "portal_nav": portal_nav,
        "portal_groups": portal_groups,
        "portal_is_tenant": user.is_tenant,
        "portal_unread": unread,
        "portfolio_units_active": namespace == "portfolio" and name.startswith("unit-"),
    }
