"""Scoped HTTP interfaces. Each operation also enforces authorization in its service."""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Exists, OuterRef, Q
from django.forms import formset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.common.files import document_response
from apps.properties.models import Property

from . import forms, services
from .models import (
    Attachment,
    Audience,
    Cost,
    MaintenanceRequest,
    Notification,
    Priority,
    Status,
    Update,
    Vendor,
)
from .workspace import request_workspace


def area(request):
    if request.resolver_match.namespace == "tenant_maintenance":
        if not request.user.is_tenant:
            raise PermissionDenied
        return "tenant_maintenance"
    if not request.user.is_rhp_staff:
        raise PermissionDenied
    return "maintenance"


def scoped(request, public_id):
    area(request)
    return get_object_or_404(
        MaintenanceRequest.objects.visible_to(request.user).select_related(
            "property", "unit", "assigned_to", "vendor"
        ),
        public_id=public_id,
    )


def context(request, obj=None, **extra):
    result = {"namespace": area(request), "ticket": obj, **extra}
    if obj:
        action = request.resolver_match.kwargs.get("action", "")
        section = {"work": "work", "permission": "work", "share": "work", "cost": "costs"}.get(
            action, "conversations"
        )
        if request.resolver_match.url_name == "recharge":
            section = "costs"
        elif request.resolver_match.url_name == "retry":
            section = "history"
        if request.GET.get("internal") == "1" and not request.user.is_tenant:
            section = "internal"
        params = {"section": section}
        if source := extra.get("source_update"):
            source_audience = obj.audiences.filter(lease_id=source.lease_id).first()
            params["section"] = "conversations" if source_audience else "internal"
            if source_audience:
                params["audience"] = source_audience.pk
        raw = request.GET.get("audience", "")
        if raw.isdigit():
            rows = obj.audiences.all()
            if request.user.is_tenant:
                rows = rows.filter(lease__lease_tenants__tenant=request.user)
            if rows.filter(pk=raw).exists():
                params["audience"] = raw
        result["back_url"] = (
            reverse(f"{area(request)}:detail", args=[obj.public_id]) + "?" + urlencode(params)
        )
    return result


def done(request, ticket, message, *, section=None, audience=None):
    messages.success(request, message)
    if section:
        params = {"section": section}
        if audience:
            params["audience"] = audience.pk
        return redirect(
            reverse(f"{area(request)}:detail", args=[ticket.public_id]) + "?" + urlencode(params)
        )
    return redirect(f"{area(request)}:detail", public_id=ticket.public_id)


@login_required
def index(request):
    area(request)
    rows = MaintenanceRequest.objects.visible_to(request.user).select_related(
        "property", "unit", "assigned_to"
    )
    selected = request.GET.get("status", "unresolved")
    if selected not in {"all", "unresolved", *Status.values}:
        selected = "unresolved"
    flagged = Audience.objects.filter(unresolved=True)
    if request.user.is_tenant:
        flagged = flagged.filter(lease__lease_tenants__tenant=request.user)
    if selected == "unresolved":
        rows = rows.filter(
            ~Q(status__in=[Status.COMPLETED, Status.CLOSED])
            | Q(pk__in=flagged.values("request_id"))
        )
    elif selected in Status.values:
        rows = rows.filter(status=selected)
    for name, field in (
        ("property", "property_id"),
        ("unit", "unit_id"),
        ("priority", "priority"),
        ("assignment", "assigned_to_id"),
    ):
        value = request.GET.get(name, "")
        if value.isdigit():
            rows = rows.filter(**{field: int(value)})
        elif name == "assignment" and value == "unassigned":
            rows = rows.filter(assigned_to__isnull=True)
    days = request.GET.get("age", "")
    if days.isdigit():
        rows = rows.filter(created_at__lte=timezone.now() - timedelta(days=min(int(days), 36500)))
    if request.GET.get("follow_up") == "yes":
        rows = rows.filter(pk__in=flagged.values("request_id"))
    rows = rows.annotate(has_follow_up=Exists(flagged.filter(request_id=OuterRef("pk"))))
    # Never populate filters from unrestricted rows for a worker or tenant.
    visible = MaintenanceRequest.objects.visible_to(request.user)
    search = request.GET.get("q", "").strip()[:200]
    if search:
        rows = rows.filter(
            Q(title__icontains=search)
            | Q(property__name__icontains=search)
            | Q(unit__identifier__icontains=search)
        )
    completed_rows = []
    if request.user.is_tenant:
        # A tenancy's own simple queue, not the staff's portfolio filter interface.
        rows = visible.exclude(status__in=[Status.COMPLETED, Status.CLOSED]).select_related(
            "property", "unit", "assigned_to"
        )
        completed_rows = visible.filter(
            status__in=[Status.COMPLETED, Status.CLOSED]
        ).select_related("property", "unit")
    return render(
        request,
        "maintenance/index.html",
        context(
            request,
            rows=rows,
            statuses=Status.choices,
            priorities=Priority.choices,
            properties=Property.objects.filter(pk__in=visible.values("property_id")),
            assignees=User.objects.filter(pk__in=visible.values("assigned_to_id")),
            selected=selected,
            search=search,
            completed_rows=completed_rows,
            can_create=request.user.is_manager_or_above
            or (
                request.user.is_tenant
                and services.Lease.objects.current()
                .filter(lease_tenants__tenant=request.user)
                .exists()
            ),
        ),
    )


@login_required
def units(request):
    area(request)
    services.manager(request.user)
    form = forms.LocationForm(request.GET)
    return render(request, "maintenance/unit_options.html", {"field": form["unit"]})


@login_required
def create(request):
    area(request)
    if not request.user.is_tenant:
        services.manager(request.user)
        location_data = request.GET.copy()
        if "load_units" in location_data:
            location_data.pop("unit", None)
        location = forms.LocationForm(location_data or None)
        if request.method != "POST" and ("continue" not in request.GET or not location.is_valid()):
            return render(
                request,
                "maintenance/location.html",
                context(request, form=location, title="Choose maintenance location"),
            )
    initial = (
        location.cleaned_data if not request.user.is_tenant and request.method == "GET" else {}
    )
    initial = {key: value.pk if value else "" for key, value in initial.items()}
    form = forms.RequestForm(
        request.POST or None, request.FILES or None, actor=request.user, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        lease = data.get("lease")
        try:
            ticket = services.create_request(
                actor=request.user,
                lease=lease,
                property=lease.unit.property if lease else data["property"],
                unit=(lease.unit if data["location"] == "unit" else None)
                if lease
                else data.get("unit"),
                title=data["title"],
                description=data["description"],
                category=data["category"],
                permission=data.get("permission", False),
                files=data["files"],
                portal_base=request.build_absolute_uri("/"),
            )
            return done(request, ticket, f"Maintenance request “{ticket.title}” submitted.")
        except ValidationError as error:
            form.add_error(None, error)
    location_summary = {}
    if not request.user.is_tenant:
        selected_location = forms.LocationForm(
            request.POST if request.method == "POST" else initial
        )
        selected_location.is_valid()
        location_summary = selected_location.cleaned_data
    return render(
        request,
        "maintenance/form.html",
        context(
            request,
            form=form,
            title="Request maintenance",
            button="Submit request",
            location_summary=location_summary,
        ),
    )


@login_required
def detail(request, public_id):
    ticket = scoped(request, public_id)
    updates = (
        Update.objects.visible_to(request.user)
        .filter(request=ticket)
        .select_related("author", "lease__unit__property")
        .prefetch_related("attachments", "revisions__actor")
    )
    audiences = ticket.audiences.select_related("lease__unit__property", "permission_by")
    if request.user.is_tenant:
        audiences = audiences.filter(lease__lease_tenants__tenant=request.user).distinct()
    workspace = request_workspace(request, ticket, audiences)
    selected = workspace["selected_audience"]
    if workspace["request_section"] == "internal":
        updates = updates.filter(lease__isnull=True)
    else:
        updates = updates.filter(lease_id=selected.lease_id) if selected else updates.none()
    milestones = updates.filter(kind__in=["STATUS", "PERMISSION"])
    updates = updates.exclude(kind__in=["STATUS", "PERMISSION"])
    tenant_location_matches = False
    if request.user.is_tenant and selected:
        from apps.leases.views import visible_lease_for

        visible = visible_lease_for(request.user)
        tenant_location_matches = bool(visible and visible.pk == selected.lease_id)
    costs, notices, total = [], [], Decimal("0.00")
    if request.user.is_manager_or_above:
        costs = list(
            ticket.costs.filter(corrects__isnull=True).prefetch_related(
                "corrections", "attachments", "recharges__charge"
            )
        )
        for cost in costs:
            cost.recharged = services.net_recharges(cost)
            total += cost.net_amount
        notices = (
            Notification.objects.filter(update__request=ticket)
            .select_related("recipient", "update")
            .prefetch_related("deliveries")
            .order_by("-pk")
        )
    return render(
        request,
        "maintenance/detail.html",
        context(
            request,
            ticket,
            updates=updates,
            costs=costs,
            total=total,
            notices=notices,
            milestones=milestones,
            tenant_location_matches=tenant_location_matches,
            history=AuditEvent.objects.filter(
                object_type="maintenance.MaintenanceRequest", object_id=ticket.pk
            )
            .select_related("actor")
            .order_by("-created_at", "-pk")[:50]
            if request.user.is_manager_or_above
            else [],
            **workspace,
        ),
    )


@login_required
def action(request, public_id, action):
    ticket = scoped(request, public_id)
    actor = request.user
    options = {
        "update": (forms.UpdateForm, "Add update", "Save update"),
        "work": (forms.WorkForm, "Manage work", "Save work details"),
        "share": (forms.ShareForm, "Share request with a tenancy", "Share request"),
        "permission": (forms.PermissionForm, "Update entry permission", "Update entry permission"),
        "follow-up": (forms.UpdateForm, "Report unresolved work", "Flag unresolved work"),
        "review-follow-up": (
            forms.UpdateForm,
            "Respond to unresolved work",
            "Send response and mark reviewed",
        ),
        "cost": (forms.CostForm, "Record repair expense or correction", "Record expense"),
    }
    if action not in options:
        raise Http404
    if action in ("share", "cost", "review-follow-up"):
        services.manager(actor)
    if action == "permission" and not actor.is_tenant:
        services.manager(actor)
    if action == "work" and actor.is_tenant:
        raise PermissionDenied
    if action == "follow-up" and not actor.is_tenant:
        raise PermissionDenied
    cls, title, button = options[action]
    kwargs = {"request": ticket}
    if action in ("update", "permission", "follow-up", "review-follow-up"):
        kwargs["actor"] = actor
    if action == "permission":
        kwargs["audience_id"] = request.GET.get("audience")
    if action == "work":
        if not actor.is_manager_or_above:
            title, button = "Record progress", "Save progress"
        kwargs = {
            "actor": actor,
            "initial": {
                key: getattr(ticket, key)
                for key in (
                    "status",
                    "priority",
                    "assigned_to",
                    "vendor",
                    "scheduled_for",
                    "schedule_window",
                )
            },
        }
    form = cls(request.POST or None, request.FILES or None, **kwargs)
    if not form.is_bound and action in ("update", "follow-up", "review-follow-up"):
        audience_id = request.GET.get("audience")
        if audience_id is not None:
            audience = (
                get_object_or_404(form.fields["audience"].queryset, pk=audience_id)
                if audience_id.isdigit()
                else None
            )
            if audience is None:
                raise Http404
            form.initial["audience"] = audience.pk
    if action in ("follow-up", "review-follow-up"):
        del form.fields["files"]
        form.fields["audience"].required = True
        form.fields["audience"].empty_label = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        base = request.build_absolute_uri("/")
        try:
            if action == "update":
                services.add_update(
                    ticket,
                    actor=actor,
                    body=data["body"],
                    lease_id=data["audience"].lease_id if data["audience"] else None,
                    files=data["files"],
                    portal_base=base,
                )
            elif action == "work":
                services.change_work(ticket, actor=actor, portal_base=base, **data)
            elif action == "share":
                services.share_request(ticket, actor=actor, portal_base=base, **data)
            elif action == "permission":
                services.set_entry_permission(
                    ticket,
                    actor=actor,
                    lease_id=data["audience"].lease_id,
                    permission=data["permission"],
                    source_note=data.get("source_note", ""),
                )
            elif action == "follow-up":
                services.follow_up(
                    ticket, actor=actor, lease_id=data["audience"].lease_id, body=data["body"]
                )
            elif action == "review-follow-up":
                services.review_follow_up(
                    ticket,
                    actor=actor,
                    lease_id=data["audience"].lease_id,
                    body=data["body"],
                    portal_base=base,
                )
            elif action == "cost":
                services.record_cost(ticket, actor=actor, **data)
            completed = {
                "update": "Update added",
                "work": "Work details updated",
                "share": "Request shared",
                "permission": "Entry permission updated",
                "follow-up": "Unresolved work flagged",
                "review-follow-up": "Response sent and follow-up marked reviewed",
                "cost": f"Repair expense of ${data.get('amount', Decimal('0')):,.2f} recorded",
            }[action]
            audience = data.get("audience")
            section = {"work": "work", "permission": "work", "share": "work", "cost": "costs"}.get(
                action, "conversations" if audience else "internal"
            )
            return done(
                request,
                ticket,
                f"{completed} for “{ticket.title}”.",
                section=section,
                audience=audience,
            )
        except ValidationError as error:
            form.add_error(None, error)
    return render(
        request,
        "maintenance/form.html",
        context(
            request,
            ticket,
            form=form,
            title=title,
            button=button,
            permission_form=action == "permission",
        ),
    )


@login_required
def update_action(request, public_id, pk, operation):
    ticket = scoped(request, public_id)
    if request.user.is_tenant:
        raise PermissionDenied
    update = get_object_or_404(Update, request=ticket, pk=pk)
    if operation == "publish":
        services.manager(request.user)
        if update.lease_id:
            raise Http404
        form = forms.PublishForm(request.POST or None, request=ticket)
        title, button = "Publish internal note", "Publish to selected tenancy"
    elif operation == "edit":
        if update.author.is_tenant or (
            update.author_id != request.user.pk and not request.user.is_manager_or_above
        ):
            raise PermissionDenied
        form = forms.EditForm(request.POST or None, initial={"body": update.body})
        title, button = "Correct staff update", "Save correction"
    else:
        raise Http404
    if request.method == "POST" and form.is_valid():
        try:
            if operation == "publish":
                services.publish_update(
                    update,
                    actor=request.user,
                    lease=form.cleaned_data["audience"].lease,
                    portal_base=request.build_absolute_uri("/"),
                )
            else:
                services.edit_update(update, actor=request.user, **form.cleaned_data)
            audience = (
                form.cleaned_data["audience"]
                if operation == "publish"
                else ticket.audiences.filter(lease_id=update.lease_id).first()
            )
            return done(
                request,
                ticket,
                f"{title} completed for “{ticket.title}”.",
                section="conversations" if audience else "internal",
                audience=audience,
            )
        except ValidationError as error:
            form.add_error(None, error)
    return render(
        request,
        "maintenance/form.html",
        context(
            request,
            ticket,
            form=form,
            title=title,
            button=button,
            publication=update if operation == "publish" else None,
            source_update=update,
        ),
    )


@login_required
def recharge(request, public_id, pk):
    ticket = scoped(request, public_id)
    services.manager(request.user)
    cost = get_object_or_404(Cost, request=ticket, pk=pk, corrects__isnull=True)
    eligible_count = services.eligible_leases(ticket).count()
    formset_class = formset_factory(
        forms.AllocationForm, extra=max(1, eligible_count), max_num=100, validate_max=True
    )
    formset = formset_class(request.POST or None, form_kwargs={"request": ticket})
    error = None
    if request.method == "POST":
        try:
            if "back" in request.POST:
                data = services.read_review(
                    request.POST.get("review", ""), actor=request.user, cost=cost
                )
                from datetime import date

                formset = formset_class(
                    initial=[
                        {**row, "due": date.fromisoformat(row["due"])} for row in data["rows"]
                    ],
                    form_kwargs={"request": ticket},
                )
                return render(
                    request,
                    "maintenance/form.html",
                    context(
                        request,
                        ticket,
                        formset=formset,
                        title="Prepare tenant recharge",
                        button="Review proposed charges",
                        cost=cost,
                    ),
                )
            if "confirm" in request.POST:
                rows = services.confirm_recharge(
                    cost, actor=request.user, token=request.POST.get("review", "")
                )
                return done(
                    request,
                    ticket,
                    f"{len(rows)} reviewed repair charge(s) posted for “{ticket.title}”.",
                    section="costs",
                )
            if formset.is_valid():
                allocations = [
                    {**form.cleaned_data, "lease": form.cleaned_data["lease"].pk}
                    for form in formset
                    if form.cleaned_data
                ]
                token = services.review_recharge(cost, actor=request.user, allocations=allocations)
                data = services.read_review(token, actor=request.user, cost=cost)
                proposed = sum((Decimal(row["amount"]) for row in data["rows"]), Decimal("0.00"))
                from datetime import date

                rows = [
                    {
                        **row,
                        "due": date.fromisoformat(row["due"]),
                        "tenancy": services.Lease.objects.get(pk=row["lease"]),
                    }
                    for row in data["rows"]
                ]
                return render(
                    request,
                    "maintenance/recharge_review.html",
                    context(
                        request,
                        ticket,
                        cost=cost,
                        rows=rows,
                        review=token,
                        previous=services.net_recharges(cost),
                        proposed=proposed,
                        difference=services.net_recharges(cost) + proposed - cost.net_amount,
                    ),
                )
        except ValidationError as exc:
            error = " ".join(exc.messages)
    return render(
        request,
        "maintenance/form.html",
        context(
            request,
            ticket,
            formset=formset,
            error=error,
            title="Prepare tenant recharge",
            button="Review proposed charges",
            cost=cost,
        ),
    )


@login_required
def download(request, public_id):
    area(request)
    rows = Attachment.objects.filter(removed_at__isnull=True)
    if request.user.is_manager_or_above:
        pass
    else:
        rows = rows.filter(update__in=Update.objects.visible_to(request.user))
    attachment = get_object_or_404(rows, public_id=public_id)
    try:
        return document_response(attachment.file, filename=attachment.original_name)
    except FileNotFoundError, OSError, ValueError:
        raise Http404 from None


@login_required
def remove(request, public_id):
    area(request)
    if request.user.role not in ("ADMIN", "SUPERADMIN") and not request.user.is_superuser:
        raise PermissionDenied
    attachment = get_object_or_404(
        Attachment.objects.select_related("update__request", "cost__request"), public_id=public_id
    )
    ticket = attachment.update.request if attachment.update_id else attachment.cost.request
    form = forms.RemovalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.remove_attachment(
            attachment, actor=request.user, reason=form.cleaned_data["reason"]
        )
        return done(
            request,
            ticket,
            f"Attachment “{attachment.original_name}” removed; audit history retained.",
        )
    return render(
        request,
        "maintenance/form.html",
        context(
            request,
            ticket,
            form=form,
            title=f"Remove {attachment.original_name}",
            button="Remove attachment",
        ),
    )


@login_required
def vendors(request, pk=None):
    area(request)
    services.manager(request.user)
    vendor = get_object_or_404(Vendor, pk=pk) if pk else None
    form = forms.VendorForm(request.POST or None, instance=vendor)
    if request.method == "POST" and form.is_valid():
        vendor = form.save()
        services.record(
            actor=request.user,
            action=services.AuditAction.MAINTENANCE_CHANGED,
            obj=vendor,
            summary="Vendor updated.",
            active=vendor.is_active,
        )
        messages.success(request, f"Vendor “{vendor.name}” saved.")
        return redirect("maintenance:vendors")
    return render(
        request,
        "maintenance/vendors.html",
        context(
            request, form=form, vendors=Vendor.objects.all(), title="Vendors", button="Save vendor"
        ),
    )


@login_required
def retry(request, pk):
    area(request)
    services.manager(request.user)
    notice = get_object_or_404(Notification.objects.select_related("update__request"), pk=pk)
    if request.method == "POST":
        services.retry_notification(notice, actor=request.user)
        return done(
            request,
            notice.update.request,
            "Email retry requested. Check delivery status below.",
            section="history",
        )
    return render(
        request, "maintenance/retry.html", context(request, notice.update.request, notice=notice)
    )
