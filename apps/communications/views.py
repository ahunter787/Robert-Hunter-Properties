from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import BigIntegerField, Exists, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.common.files import document_response
from apps.leases.models import Lease

from . import delivery, forms, services
from .models import (
    Announcement,
    Attachment,
    Conversation,
    ConversationPreference,
    Message,
    Notification,
    QuickReply,
    ReadPosition,
)


def namespace(request):
    services.authorize(request.user)
    tenant = request.resolver_match.namespace == "tenant_communications"
    if tenant != request.user.is_tenant:
        raise PermissionDenied
    return "tenant_communications" if tenant else "communications"


def context(request, section="messages", **extra):
    ns = namespace(request)
    params = request.GET.copy()
    params.pop("page", None)
    return {
        "namespace": ns,
        "communication_section": section,
        "now": timezone.now(),
        "filter_query": params.urlencode(),
        "communication_tabs": [
            {"label": "Messages", "url": reverse(f"{ns}:index"), "active": section == "messages"},
            {
                "label": "Announcements",
                "url": reverse(f"{ns}:announcements"),
                "active": section == "announcements",
            },
        ],
        **extra,
    }


def scoped_conversation(request, public_id):
    namespace(request)
    return get_object_or_404(
        Conversation.objects.visible_to(request.user).select_related("lease__unit__property"),
        public_id=public_id,
    )


def scoped_notice(request, public_id):
    namespace(request)
    return get_object_or_404(Announcement.objects.visible_to(request.user), public_id=public_id)


def feedback(form, error):
    form.add_error(None, error)


def identifier(raw):
    """Accept only bounded decimal database IDs, never Unicode digit lookalikes."""
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 19 or int(raw) > 2**63 - 1:
        raise Http404
    return int(raw)


def with_unread(rows, actor):
    position = ReadPosition.objects.filter(conversation=OuterRef("pk"), user=actor).values(
        "message_id"
    )[:1]
    rows = rows.annotate(
        last_read=Coalesce(Subquery(position), Value(0), output_field=BigIntegerField())
    )
    unread = Message.objects.filter(
        conversation=OuterRef("pk"), pk__gt=OuterRef("last_read")
    ).exclude(author=actor)
    return rows.annotate(unread=Exists(unread))


@login_required
def index(request):
    ns = namespace(request)
    rows = (
        Conversation.objects.visible_to(request.user)
        .select_related("lease__unit__property")
        .prefetch_related("participants__user")
    )
    if request.user.is_manager_or_above:
        rows = rows.filter(messages__isnull=False).distinct()
    q = request.GET.get("q", "").strip()[:160]
    if q:
        rows = rows.filter(
            Q(subject__icontains=q)
            | Q(participants__user__first_name__icontains=q)
            | Q(participants__user__last_name__icontains=q)
            | Q(lease__unit__property__name__icontains=q)
            | Q(lease__unit__identifier__icontains=q)
        ).distinct()
    for param, field in (
        ("property", "lease__unit__property_id"),
        ("unit", "lease__unit_id"),
        ("tenant", "participants__user_id"),
    ):
        if raw := request.GET.get(param):
            rows = rows.filter(**{field: identifier(raw)})
    state = request.GET.get("state", "")
    if state and state not in Conversation.State.values:
        raise Http404
    if state:
        rows = rows.filter(state=state)
    archived = request.GET.get("archived") == "1"
    preferences = ConversationPreference.objects.filter(
        conversation=OuterRef("pk"), user=request.user
    )
    rows = rows.annotate(my_archived=Exists(preferences.filter(archived_at__isnull=False)))
    rows = rows.filter(my_archived=archived)
    rows = with_unread(rows, request.user)
    if request.GET.get("unread") == "1":
        rows = rows.filter(unread=True)
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "communications/index.html",
        context(
            request,
            page=Paginator(rows, 25).get_page(request.GET.get("page")),
            search=q,
            states=Conversation.State.choices,
            filter_query=params.urlencode(),
            new_url=reverse(f"{ns}:new"),
            inbox_filters=forms.InboxFilters(
                actor=request.user,
                initial={key: request.GET.get(key) for key in ("property", "unit", "tenant")},
            ),
        ),
    )


def thread_context(request, row, form=None):
    pages = Paginator(row.messages.select_related("author").prefetch_related("attachments"), 25)
    page = pages.get_page(request.GET.get("page") or pages.num_pages)
    items = list(page.object_list)
    last = items[-1].pk if items else 0
    receipt = (
        signing.dumps(
            {"actor": request.user.pk, "conversation": row.pk, "message": last},
            salt="communications.read",
        )
        if last
        else ""
    )
    return context(
        request,
        conversation=row,
        page=page,
        message_rows=items,
        participants=row.participants.select_related("user"),
        form=form or forms.MessageForm(),
        writable=services.can_send(row, request.user),
        last_id=last,
        read_receipt=receipt,
        poll=not page.has_next(),
        work_form=forms.WorkForm(),
        quick_replies=QuickReply.objects.filter(is_active=True)
        .filter(Q(property__isnull=True) | Q(property=row.lease.unit.property))
        .order_by("label", "pk")
        if request.user.is_manager_or_above
        else [],
        events=row.events.select_related("actor").order_by("pk")
        if request.user.is_manager_or_above
        else [],
    )


@login_required
def conversation(request, public_id):
    row = scoped_conversation(request, public_id)
    form = forms.MessageForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.send_message(
                row,
                actor=request.user,
                portal_base=request.build_absolute_uri("/"),
                **form.cleaned_data,
            )
            return redirect(f"{namespace(request)}:conversation", public_id=row.public_id)
        except ValidationError as error:
            feedback(form, error)
    return render(request, "communications/conversation.html", thread_context(request, row, form))


@login_required
def updates(request, public_id):
    row = scoped_conversation(request, public_id)
    raw = request.GET.get("after", "0")
    after = identifier(raw)
    if after and not row.messages.filter(pk=after).exists():
        raise Http404
    items = list(
        row.messages.filter(pk__gt=after)
        .select_related("author")
        .prefetch_related("attachments")[:25]
    )
    last = items[-1].pk if items else after
    receipt = (
        signing.dumps(
            {"actor": request.user.pk, "conversation": row.pk, "message": last},
            salt="communications.read",
        )
        if last
        else ""
    )
    return render(
        request,
        "communications/message_batch.html",
        context(request, message_rows=items, conversation=row, last_id=last, read_receipt=receipt),
    )


@login_required
def read(request, public_id):
    row = scoped_conversation(request, public_id)
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        data = signing.loads(
            request.POST.get("receipt", ""), salt="communications.read", max_age=3600
        )
        if data["actor"] != request.user.pk or data["conversation"] != row.pk:
            raise Http404
        services.mark_read(row, actor=request.user, message_id=data["message"])
    except (signing.BadSignature, KeyError, Message.DoesNotExist) as error:
        raise Http404 from error
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return HttpResponse(status=204)
    return redirect(f"{namespace(request)}:conversation", public_id=row.public_id)


@login_required
def work(request, public_id):
    row = scoped_conversation(request, public_id)
    services.authorize(request.user, manager=True)
    if request.method != "POST":
        return HttpResponse(status=405)
    form = forms.WorkForm(request.POST)
    if form.is_valid():
        try:
            services.change_work(
                row,
                actor=request.user,
                action=request.POST.get("action"),
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, f"Conversation updated: {row.subject}.")
            return redirect("communications:conversation", public_id=row.public_id)
        except ValidationError as error:
            feedback(form, error)
    data = thread_context(request, row)
    data["work_form"] = form
    return render(request, "communications/conversation.html", data)


@login_required
def new(request):
    ns = namespace(request)
    if token := request.POST.get("review"):
        form = forms.MessageForm(request.POST, request.FILES)
        try:
            reviewed = services.conversation_review(token, request.user)
            if form.is_valid():
                message = services.start_conversation(
                    actor=request.user,
                    review=token,
                    portal_base=request.build_absolute_uri("/"),
                    **form.cleaned_data,
                )
                return redirect(f"{ns}:conversation", public_id=message.conversation.public_id)
        except ValidationError as error:
            feedback(form, error)
            reviewed = None
        return render(
            request,
            "communications/new_review.html",
            context(
                request,
                form=form,
                review=token,
                reviewed=reviewed,
                lease=Lease.objects.filter(pk=reviewed["lease"])
                .select_related("unit__property")
                .first()
                if reviewed
                else None,
                recipients=User.objects.filter(pk__in=reviewed["participants"]) if reviewed else [],
            ),
        )
    location = forms.LocationForm(request.GET or None, actor=request.user)
    if request.method == "GET" and not location.is_valid():
        return render(
            request,
            "communications/form.html",
            context(
                request, form=location, title="Choose tenancy", button="Continue", method="get"
            ),
        )
    form = forms.ConversationForm(
        request.POST or None,
        actor=request.user,
        initial={"lease": location.cleaned_data["lease"].pk} if request.method == "GET" else {},
    )
    if request.method == "POST" and form.is_valid():
        try:
            token, data = services.review_conversation(actor=request.user, **form.cleaned_data)
            return render(
                request,
                "communications/new_review.html",
                context(
                    request,
                    form=forms.MessageForm(),
                    review=token,
                    reviewed=data,
                    lease=form.cleaned_data["lease"],
                    recipients=User.objects.filter(pk__in=data["participants"]),
                ),
            )
        except ValidationError as error:
            feedback(form, error)
    return render(
        request,
        "communications/form.html",
        context(
            request,
            form=form,
            title="New conversation",
            button="Review participants",
            method="post",
        ),
    )


@login_required
def attachment(request, public_id):
    namespace(request)
    obj = get_object_or_404(
        Attachment.objects.select_related("message"),
        public_id=public_id,
        message__conversation__in=Conversation.objects.visible_to(request.user),
    )
    return document_response(obj.file, filename=obj.display_name)


@login_required
def announcements(request):
    namespace(request)
    now = timezone.now()
    rows = []
    for row in Announcement.objects.visible_to(request.user).prefetch_related("versions"):
        latest = row.latest
        active = (
            row.published_at
            and not row.withdrawn_at
            and latest
            and (not latest.expires_at or latest.expires_at > now)
        )
        if request.GET.get("archive") == "1":
            include = bool(row.published_at and not active)
        else:
            include = active or (request.user.is_manager_or_above and not row.published_at)
        if include:
            row.display_version = latest or row
            rows.append(row)
    rows.sort(key=lambda a: (bool(a.display_version.important), a.pk), reverse=True)
    return render(
        request,
        "communications/announcements.html",
        context(
            request,
            "announcements",
            page=Paginator(rows, 25).get_page(request.GET.get("page")),
            archive=request.GET.get("archive") == "1",
        ),
    )


@login_required
def announcement(request, public_id):
    row = scoped_notice(request, public_id)
    own = row.recipients.filter(user=request.user).select_related("lease__unit__property")
    return render(
        request,
        "communications/announcement.html",
        context(
            request,
            "announcements",
            announcement=row,
            version=row.latest or row,
            versions=row.versions.select_related("author").order_by("-pk"),
            notice_events=row.events.select_related("actor"),
            recipients=row.recipients.select_related("user", "lease__unit__property")
            if request.user.is_manager_or_above
            else [],
            own_leases=Lease.objects.current()
            .filter(pk__in=own.values("lease_id"))
            .for_tenant(request.user),
            notifications=Notification.objects.filter(version__announcement=row)
            .select_related("recipient")
            .prefetch_related("attempts")
            if request.user.is_manager_or_above
            else [],
            action_form=forms.ActionForm(),
        ),
    )


@login_required
def draft(request, public_id=None):
    namespace(request)
    services.authorize(request.user, manager=True)
    row = scoped_notice(request, public_id) if public_id else None
    if row and row.published_at:
        raise Http404
    initial = (
        {name: getattr(row, name) for name in ("title", "body", "important", "expires_at")}
        if row
        else {}
    )
    initial["properties"] = row.property_ids if row else []
    form = forms.DraftForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            row = services.save_draft(actor=request.user, announcement=row, **form.cleaned_data)
            return redirect("communications:announcement", public_id=row.public_id)
        except ValidationError as error:
            feedback(form, error)
    return render(
        request,
        "communications/form.html",
        context(
            request,
            "announcements",
            title="Edit draft" if row else "New announcement",
            form=form,
            button="Save draft",
            method="post",
        ),
    )


@login_required
def publish(request, public_id):
    row = scoped_notice(request, public_id)
    services.authorize(request.user, manager=True)
    if token := request.POST.get("review"):
        try:
            if services.announcement_review(token, request.user)["pk"] != row.pk:
                raise Http404
            services.publish_announcement(
                actor=request.user, review=token, portal_base=request.build_absolute_uri("/")
            )
            messages.success(request, "Announcement published.")
            return redirect("communications:announcement", public_id=row.public_id)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("communications:publish", public_id=row.public_id)
    version = row.latest or row
    initial = {
        name: getattr(version, name) for name in ("title", "body", "important", "expires_at")
    }
    form = forms.NoticeContentForm(
        request.POST or None, initial=initial, correction=bool(row.published_at)
    )
    if request.method == "POST" and form.is_valid():
        try:
            token, data = services.review_announcement(row, actor=request.user, **form.cleaned_data)
            ids = {p[1] for p in data["audience"]}
            users = User.objects.filter(pk__in=ids)
            return render(
                request,
                "communications/publish_review.html",
                context(
                    request,
                    "announcements",
                    review=token,
                    reviewed=data,
                    announcement=row,
                    recipient_count=len(ids),
                    tenancy_count=len({p[0] for p in data["audience"]}),
                    email_count=users.filter(is_active=True).exclude(email="").count(),
                    recipient_rows=[
                        (
                            Lease.objects.select_related("unit__property").get(pk=lease_id),
                            User.objects.get(pk=user_id),
                        )
                        for lease_id, user_id in data["audience"]
                    ],
                ),
            )
        except ValidationError as error:
            feedback(form, error)
    return render(
        request,
        "communications/form.html",
        context(
            request,
            "announcements",
            form=form,
            title="Correct announcement" if row.published_at else "Review publication",
            button="Review recipients",
            method="post",
        ),
    )


@login_required
def withdraw(request, public_id):
    row = scoped_notice(request, public_id)
    services.authorize(request.user, manager=True)
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        services.withdraw_announcement(
            row, actor=request.user, reason=request.POST.get("reason", "")
        )
        messages.success(request, "Announcement withdrawn. Its history is retained.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("communications:announcement", public_id=row.public_id)


@login_required
def followup(request, public_id):
    row = scoped_notice(request, public_id)
    if request.method != "POST":
        return HttpResponse(status=405)
    lease = get_object_or_404(Lease, pk=identifier(request.POST.get("lease", "")))
    try:
        thread = services.announcement_followup(row, actor=request.user, lease=lease)
        return redirect(f"{namespace(request)}:conversation", public_id=thread.public_id)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(f"{namespace(request)}:announcement", public_id=row.public_id)


@login_required
def delivery_list(request):
    namespace(request)
    services.authorize(request.user, manager=True)
    rows = (
        Notification.objects.exclude(status="SENT")
        .select_related("recipient")
        .prefetch_related("attempts")
        .order_by("-pk")
    )
    return render(
        request,
        "communications/deliveries.html",
        context(request, page=Paginator(rows, 25).get_page(request.GET.get("page"))),
    )


@login_required
def retry(request, pk):
    namespace(request)
    services.authorize(request.user, manager=True)
    notice = get_object_or_404(Notification, pk=pk)
    form = forms.ActionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            delivery.retry(
                notice,
                actor=request.user,
                acknowledge_duplicate=form.cleaned_data["acknowledge_duplicate"],
            )
            return redirect("communications:deliveries")
        except ValidationError as error:
            feedback(form, error)
    return render(
        request,
        "communications/form.html",
        context(
            request,
            form=form,
            method="post",
            title=f"Retry email to {notice.recipient.display_name}",
            guidance=(
                "The previous delivery may have succeeded. "
                "Confirm the duplicate-delivery warning for uncertain outcomes."
            ),
            button="Retry email",
        ),
    )


@login_required
def quick_reply_list(request):
    services.authorize(request.user, manager=True)
    rows = QuickReply.objects.select_related("property").order_by("label", "pk")
    if request.GET.get("archived") != "1":
        rows = rows.filter(is_active=True)
    return render(
        request,
        "communications/quick_replies.html",
        context(request, section="messages", quick_replies=rows),
    )


@login_required
def quick_reply_edit(request, pk=None):
    services.authorize(request.user, manager=True)
    instance = get_object_or_404(QuickReply, pk=pk) if pk else None
    form = forms.QuickReplyForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        if instance is None:
            row.created_by = request.user
        row.save()
        messages.success(request, "Quick reply saved.")
        return redirect("communications:quick-replies")
    return render(
        request,
        "communications/quick_reply_form.html",
        context(request, section="messages", form=form, reply=instance),
    )


@login_required
def quick_reply_toggle(request, pk):
    services.authorize(request.user, manager=True)
    if request.method != "POST":
        return HttpResponse(status=405)
    row = get_object_or_404(QuickReply, pk=pk)
    row.is_active = not row.is_active
    row.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Quick reply updated.")
    return redirect("communications:quick-replies")


@login_required
def conversation_archive(request, public_id):
    row = scoped_conversation(request, public_id)
    if request.method != "POST":
        return HttpResponse(status=405)
    services.set_preference(
        row,
        actor=request.user,
        archived=request.POST.get("archived") == "1",
    )
    messages.success(request, "Conversation inbox updated.")
    return redirect("communications:conversation", public_id=row.public_id)


@login_required
def conversation_mute(request, public_id):
    row = scoped_conversation(request, public_id)
    if request.method != "POST":
        return HttpResponse(status=405)
    services.set_preference(row, actor=request.user, mute=request.POST.get("mute") == "1")
    messages.success(request, "Email preference updated.")
    return redirect("communications:conversation", public_id=row.public_id)


@login_required
def conversation_note(request, public_id):
    row = scoped_conversation(request, public_id)
    services.authorize(request.user, manager=True)
    if request.method != "POST":
        return HttpResponse(status=405)
    form = forms.InternalNoteForm(request.POST)
    if form.is_valid():
        services.add_internal_note(row, actor=request.user, body=form.cleaned_data["body"])
        messages.success(request, "Internal note added.")
    else:
        messages.error(request, "Write a note before saving.")
    return redirect("communications:conversation", public_id=row.public_id)


@login_required
def conversation_export(request, public_id, fmt):
    row = scoped_conversation(request, public_id)
    services.authorize(request.user, manager=True)
    if fmt not in ("txt", "csv"):
        raise Http404
    if fmt == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "author", "body", "attachments"])
        for message in row.messages.select_related("author").prefetch_related("attachments"):
            writer.writerow(
                [
                    message.created_at.isoformat(),
                    message.author.display_name,
                    message.body,
                    "; ".join(item.display_name for item in message.attachments.all()),
                ]
            )
        content, content_type, filename = (
            output.getvalue(),
            "text/csv",
            f"conversation-{row.public_id}.csv",
        )
    else:
        lines = [f"{row.subject}\n{row.lease.unit.label}\n"]
        for message in row.messages.select_related("author"):
            lines.append(
                f"{message.created_at.isoformat()} · {message.author.display_name}\n"
                f"{message.body}\n"
            )
        content, content_type, filename = (
            "\n".join(lines),
            "text/plain",
            f"conversation-{row.public_id}.txt",
        )
    from apps.audit.services import record

    record(
        request.user,
        "COMMUNICATION_CHANGED",
        obj=row,
        summary=f"Conversation transcript exported ({fmt}).",
    )
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
