from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.communications.models import Conversation
from apps.communications.views import with_unread
from apps.leases.models import Lease
from apps.ledger import services as ledger
from apps.maintenance.models import Audience, MaintenanceRequest, Priority, Status
from apps.properties.models import Property, Unit

ZERO = Decimal("0.00")
CATEGORIES = {
    "RENT": "Rent",
    "NNN": "Triple-net charges",
    "RESPONSIBILITY": "Expense recoveries",
    "MANUAL": "One-time charges",
    "OPENING": "Opening balances",
    "ADJUSTMENT": "Other credits and adjustments",
}


def authorize(user):
    if not user.is_authenticated or not user.is_active or not user.is_manager_or_above:
        raise PermissionDenied


@dataclass
class Row:
    label: str
    context: str
    url: str
    amount: Decimal | None = None
    date: object = None
    status: str = ""
    corrections: list = field(default_factory=list)
    original: Decimal | None = None


@dataclass
class Metric:
    key: str
    label: str
    help: str
    money: bool = False
    rows: list = field(default_factory=list)

    @property
    def value(self):
        return sum((r.amount for r in self.rows), ZERO) if self.money else len(self.rows)

    @property
    def url(self):
        return reverse("manage:dashboard-detail", args=[self.key])


def project(user):
    authorize(user)
    now = timezone.now()
    today = timezone.localtime(now).date()
    month = today.replace(day=1)
    definitions = [
        ("past-due", "Past due", "Unpaid posted charges with a due date before today.", True),
        ("overdue-accounts", "Overdue accounts", "Tenancies with a past-due amount.", False),
        ("due-now", "Due now", "Includes past-due amounts and charges due today.", True),
        (
            "upcoming",
            "Upcoming charges",
            "Unpaid posted charges due after today; not expected unposted rent.",
            True,
        ),
        (
            "balances",
            "Account balances",
            "Positive account balances, including upcoming posted charges.",
            True,
        ),
        (
            "credits",
            "Credit balances",
            "Credits are kept separate from other tenancies' debts.",
            True,
        ),
        (
            "month-charges",
            "Charges due this month",
            "All posted categories, corrected against their original due dates.",
            True,
        ),
        (
            "month-payments",
            "Cleared payments received this month",
            "Payment dates in this month; excludes pending, voided and reversed payments.",
            True,
        ),
        (
            "maintenance",
            "Unresolved requests",
            "Open work and tenant follow-ups awaiting review.",
            False,
        ),
        (
            "urgent",
            "High or urgent priority",
            "Unresolved requests at high or urgent priority.",
            False,
        ),
        ("in-progress", "Work in progress", "Requests currently marked In progress.", False),
        (
            "aging",
            "Open over seven days",
            "Unresolved requests created seven or more days ago.",
            False,
        ),
        ("follow-ups", "Tenant follow-ups", "Requests with an unresolved tenant follow-up.", False),
        (
            "needs-reply",
            "Needs RHP reply",
            "Conversations awaiting a reply from RHP.",
            False,
        ),
        (
            "unread",
            "Unread for you",
            "Conversations containing messages you have not marked read.",
            False,
        ),
        ("properties", "Properties in service", "Properties currently in service.", False),
        ("units", "Units in service", "Units currently in service.", False),
        ("occupied", "Occupied units", "In-service units with a current active tenancy.", False),
        ("vacant", "Vacant units", "In-service units without a current active tenancy.", False),
        ("tenants", "Tenant accounts", "active accounts", False),
        ("invitations", "Invitations", "Tenant accounts awaiting password setup.", False),
        (
            "ending-30",
            "Ending within 30 days",
            "Active leases ending today through 30 days from today.",
            False,
        ),
        (
            "ending-90",
            "Ending within 90 days",
            "Includes leases ending within the next 30 days.",
            False,
        ),
    ]
    metrics = {key: Metric(key, label, help, money) for key, label, help, money in definitions}
    for kind, label in CATEGORIES.items():
        key = f"month-{kind.lower()}"
        metrics[key] = Metric(
            key, label, "Posted charges due this month, with corrections inline.", True
        )
    for account in ledger.ledger_rows():
        lease = account.lease
        url = reverse("ledger:lease-ledger", args=[lease.pk])
        label = lease.tenant_names or "Tenancy"
        context = lease.unit.label
        for key, amount in (
            ("past-due", account.arrears),
            ("due-now", account.due_now),
            ("upcoming", account.not_yet_due),
            ("balances", max(account.balance_due, ZERO)),
            ("credits", account.credit),
        ):
            if amount > ZERO:
                metrics[key].rows.append(Row(label, context, url, amount))
        if account.has_arrears:
            metrics["overdue-accounts"].rows.append(Row(label, context, url, account.arrears))
        # TransactionRow already absorbs signed corrections into their original charge.
        for transaction in account.transactions:
            charge = transaction.charge_entry
            if charge and transaction.date >= month:
                if transaction.date.year != today.year or transaction.date.month != today.month:
                    continue
                amount = transaction.charge - transaction.payment_or_credit
                row = Row(
                    charge.description,
                    f"{context} · {label}",
                    url,
                    amount,
                    transaction.date,
                    transaction.status,
                    transaction.adjustments,
                    charge.amount,
                )
                metrics["month-charges"].rows.append(row)
                metrics[f"month-{charge.kind.lower()}"].rows.append(row)
        for payment in account.effective_payments:
            if (
                payment.payment_date.year == today.year
                and payment.payment_date.month == today.month
            ):
                metrics["month-payments"].rows.append(
                    Row(label, context, url, payment.amount, payment.payment_date, "Cleared")
                )
    flagged = Audience.objects.filter(unresolved=True).values("request_id")
    requests = MaintenanceRequest.objects.visible_to(user).select_related("property", "unit")
    unresolved = requests.filter(
        ~Q(status__in=[Status.COMPLETED, Status.CLOSED]) | Q(pk__in=flagged)
    )
    populations = {
        "maintenance": unresolved,
        "urgent": unresolved.filter(priority__gte=Priority.HIGH),
        "in-progress": requests.filter(status=Status.IN_PROGRESS),
        "aging": unresolved.filter(created_at__lte=now - timedelta(days=7)),
        "follow-ups": requests.filter(pk__in=flagged),
    }
    for key, rows in populations.items():
        metrics[key].rows = [
            Row(
                r.title,
                r.unit.label if r.unit else r.property.name,
                reverse("maintenance:detail", args=[r.public_id]),
                date=r.created_at,
                status=f"{r.get_priority_display()} · {r.get_status_display()}",
            )
            for r in rows
        ]
    conversations = (
        Conversation.objects.visible_to(user)
        .filter(messages__isnull=False)
        .distinct()
        .select_related("lease__unit__property")
    )
    for key, rows in {
        "needs-reply": conversations.filter(state="NEEDS_RHP", frozen_at=None),
        "unread": with_unread(conversations, user).filter(unread=True),
    }.items():
        metrics[key].rows = [
            Row(
                r.subject,
                r.lease.unit.label,
                reverse("communications:conversation", args=[r.public_id]),
                date=r.updated_at,
                status=r.get_state_display(),
            )
            for r in rows
        ]
    metrics["properties"].rows = [
        Row(p.name, p.address_line, reverse("portfolio:property-detail", args=[p.pk]))
        for p in Property.objects.active().order_by("name", "pk")
    ]
    units = (
        Unit.objects.active()
        .select_related("property")
        .order_by("property__name", "identifier", "pk")
    )
    occupied = set(Lease.objects.current().values_list("unit_id", flat=True))
    for unit in units:
        row = Row(
            unit.identifier, unit.property.name, reverse("portfolio:unit-detail", args=[unit.pk])
        )
        metrics["units"].rows.append(row)
        metrics["occupied" if unit.pk in occupied else "vacant"].rows.append(row)
    for days in (30, 90):
        metrics[f"ending-{days}"].rows = [
            Row(
                lease.tenant_names or "Tenancy",
                lease.unit.label,
                reverse("leases:lease-detail", args=[lease.pk]),
                date=lease.end_date,
            )
            for lease in Lease.objects.expiring_within(days)
            .select_related("unit__property")
            .prefetch_related("lease_tenants__tenant")
            .order_by("end_date", "pk")
        ]
    from apps.accounts.views import _invited_accounts

    for key, users in {
        "tenants": User.objects.filter(role=Role.TENANT, is_active=True),
        "invitations": _invited_accounts().filter(role=Role.TENANT),
    }.items():
        metrics[key].rows = [
            Row(u.display_name, "Tenant account", reverse("manage:account-detail", args=[u.pk]))
            for u in users.order_by("username")
        ]
    groups = [
        (
            "Rent & Payments",
            ["past-due", "overdue-accounts", "due-now", "upcoming", "balances", "credits"],
        ),
        (
            f"{today:%B %Y}",
            ["month-charges", "month-payments", *[f"month-{k.lower()}" for k in CATEGORIES]],
        ),
        ("Maintenance", ["maintenance", "urgent", "in-progress", "aging", "follow-ups"]),
        ("Communications", ["needs-reply", "unread"]),
        ("Portfolio", ["properties", "units", "occupied", "vacant", "tenants", "invitations"]),
        ("Leases", ["ending-30", "ending-90"]),
    ]
    return {
        "updated_at": now,
        "metrics": metrics,
        "groups": [(label, [metrics[key] for key in keys]) for label, keys in groups],
    }
