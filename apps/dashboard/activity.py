"""Safe audit projection. Never render unrestricted summary or metadata text."""

from django import forms
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditEvent
from apps.common.forms import StyledForm
from apps.communications.models import Announcement, Conversation
from apps.documents.models import Document
from apps.leases.models import Lease
from apps.ledger.models import Charge, Payment
from apps.maintenance.models import Cost, MaintenanceRequest
from apps.properties.models import Property, Unit
from apps.responsibilities.models import PropertyResponsibility, ResponsibilityCycle

from .services import authorize

ACTION_LABELS = {
    **dict(AuditAction.choices),
    AuditAction.NNN_RATE_SET: "Triple-net (NNN) amount set",
}


class TenancyChoice(forms.ModelChoiceField):
    def label_from_instance(self, lease):
        return (
            f"{lease.unit.label} · "
            f"{lease.start_date:%b} {lease.start_date.day}, {lease.start_date.year}"
            f" – {lease.end_date:%b} {lease.end_date.day}, {lease.end_date.year}"
        )


# Only these types can produce a link. Unknown/removed records retain their event.
TARGETS = {
    "ledger.Charge": (
        Charge,
        "ledger:lease-ledger",
        ("lease__unit__property",),
        "lease__unit__property_id",
    ),
    "ledger.Payment": (
        Payment,
        "ledger:lease-ledger",
        ("lease__unit__property",),
        "lease__unit__property_id",
    ),
    "leases.Lease": (Lease, "leases:lease-detail", ("unit__property",), "unit__property_id"),
    "properties.Property": (Property, "portfolio:property-detail", (), "pk"),
    "properties.Unit": (Unit, "portfolio:unit-detail", ("property",), "property_id"),
    "maintenance.MaintenanceRequest": (
        MaintenanceRequest,
        "maintenance:detail",
        ("property", "unit"),
        "property_id",
    ),
    "maintenance.Cost": (
        Cost,
        "maintenance:detail",
        ("request__property",),
        "request__property_id",
    ),
    "communications.Conversation": (
        Conversation,
        "communications:conversation",
        ("lease__unit__property",),
        "lease__unit__property_id",
    ),
    "communications.Announcement": (
        Announcement,
        "communications:announcement",
        (),
        "recipients__lease__unit__property_id",
    ),
    "responsibilities.PropertyResponsibility": (
        PropertyResponsibility,
        "responsibilities:responsibility-update",
        ("property",),
        "property_id",
    ),
    "responsibilities.ResponsibilityCycle": (
        ResponsibilityCycle,
        "responsibilities:cycle-shares",
        ("responsibility__property",),
        "responsibility__property_id",
    ),
    "documents.Document": (Document, "documents:list", (), "property_id"),
    "accounts.User": (User, "manage:account-detail", (), None),
}


def visible(user):
    authorize(user)
    rows = AuditEvent.objects.all()
    if user.role != Role.SUPERADMIN and not user.is_superuser:
        rows = rows.exclude(action=AuditAction.ROLE_CHANGED)
    return rows.select_related("actor", "lease__unit__property").order_by("-created_at", "-pk")


class Filters(StyledForm):
    start = forms.DateField(
        required=False, label="From", widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        required=False, label="Through", widget=forms.DateInput(attrs={"type": "date"})
    )
    actor = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label="Changed by")
    action = forms.ChoiceField(required=False, label="Activity type")
    property = forms.ModelChoiceField(queryset=Property.objects.all(), required=False)
    tenancy = TenancyChoice(queryset=Lease.objects.all(), required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        rows = visible(user)
        self.fields["actor"].queryset = User.objects.filter(
            pk__in=rows.values("actor_id")
        ).order_by("username")
        self.fields["action"].choices = [
            ("", "All types"),
            *[
                (key, ACTION_LABELS[key])
                for key, label in AuditAction.choices
                if key != AuditAction.ROLE_CHANGED
                or user.role == Role.SUPERADMIN
                or user.is_superuser
            ],
        ]
        self.fields["tenancy"].queryset = Lease.objects.select_related("unit__property")
        for name, label in (
            ("actor", "All people"),
            ("property", "All properties"),
            ("tenancy", "All tenancies"),
        ):
            self.fields[name].empty_label = label

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return data


def filtered(user, data):
    rows = visible(user)
    for field in ("start", "end", "actor", "action", "tenancy"):
        if value := data.get(field):
            lookup = {
                "start": "created_at__date__gte",
                "end": "created_at__date__lte",
                "tenancy": "lease",
            }.get(field, field)
            rows = rows.filter(**{lookup: value})
    if prop := data.get("property"):
        scope = Q(lease__unit__property=prop)
        for kind, (model, _, _, lookup) in TARGETS.items():
            if lookup:
                ids = model.objects.filter(**{lookup: prop.pk}).values("pk")
                scope |= Q(object_type=kind, object_id__in=ids)
        rows = rows.filter(scope)
    return rows


def project(events):
    events = list(events)
    objects = {}
    for kind, (model, _, related, _) in TARGETS.items():
        ids = [e.object_id for e in events if e.object_type == kind and e.object_id]
        if ids:
            queryset = model.objects.all()
            if related:
                queryset = queryset.select_related(*related)
            objects[kind] = queryset.in_bulk(ids)
    rows = []
    for event in events:
        target = objects.get(event.object_type, {}).get(event.object_id)
        context, url = "Historical record unavailable", ""
        if event.lease_id:
            context = event.lease.unit.label
            url = reverse("ledger:lease-ledger", args=[event.lease_id])
        if target:
            model, route, _, _ = TARGETS[event.object_type]
            if model is Lease:
                context = target.unit.label
            elif model in (Property, Unit):
                context = target.name if model is Property else target.label
            elif model is MaintenanceRequest:
                context = f"{target.title} · {target.property.name}"
            elif model is Cost:
                context = target.request.property.name
            elif model is Conversation:
                context = f"{target.subject} · {target.lease.unit.label}"
            elif model is Announcement:
                context = target.title
            elif model in (Charge, Payment):
                context = target.lease.unit.label
            elif model is User:
                context = target.display_name
                if not target.is_tenant:
                    route = ""  # Staff accounts do not use the tenant account workspace.
            elif model is PropertyResponsibility:
                context = f"{target.label} · {target.property.name}"
            elif model is ResponsibilityCycle:
                context = f"{target.responsibility.label} · {target.responsibility.property.name}"
            else:
                context = target.title if model is Document else "Expense recovery"
            if route:
                key = (
                    target.request.public_id
                    if model is Cost
                    else getattr(target, "public_id", target.pk)
                )
                if model in (Charge, Payment):
                    key = target.lease_id
                url = reverse(route, args=[] if route == "documents:list" else [key])
        rows.append(
            {
                "label": ACTION_LABELS.get(event.action, "Recorded activity"),
                "context": context,
                "url": url,
                "actor": event.actor.display_name if event.actor else "Actor unavailable",
                "date": event.created_at,
            }
        )
    return rows
