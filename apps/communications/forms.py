from uuid import uuid4

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.common.forms import StyledForm, StyledModelForm
from apps.leases.models import Lease
from apps.properties.models import Property, Unit

from .models import Conversation, QuickReply


def leases_for(actor):
    rows = Lease.objects.exclude(status="DRAFT").select_related("unit__property")
    return rows if actor.is_manager_or_above else rows.current().for_tenant(actor)


class LeaseChoice(forms.ModelChoiceField):
    def label_from_instance(self, lease):
        return (
            f"{lease.unit.label} · {lease.tenant_names} · "
            f"{lease.start_date:%b %d, %Y} – {lease.end_date:%b %d, %Y}"
        )


class LocationForm(StyledForm):
    lease = LeaseChoice(queryset=Lease.objects.none(), label="Tenancy")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lease"].queryset = leases_for(actor)


class InboxFilters(StyledForm):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), required=False)
    unit = forms.ModelChoiceField(queryset=Unit.objects.none(), required=False)
    tenant = forms.ModelChoiceField(queryset=User.objects.none(), required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Conversation

        history = Conversation.objects.visible_to(actor)
        self.fields["property"].queryset = Property.objects.filter(
            units__leases__in=history.values("lease_id")
        ).distinct()
        self.fields["unit"].queryset = (
            Unit.objects.filter(leases__in=history.values("lease_id"))
            .select_related("property")
            .distinct()
        )
        self.fields["tenant"].queryset = User.objects.filter(
            participant__conversation__in=history
        ).distinct()


class ConversationForm(LocationForm):
    subject = forms.CharField(max_length=160)
    visibility = forms.ChoiceField(
        choices=Conversation.Visibility.choices,
        initial="PRIVATE",
        label="Who can read this conversation?",
    )
    tenant = forms.ModelChoiceField(
        queryset=User.objects.none(), required=False, label="Private conversation with"
    )
    followup = forms.BooleanField(
        required=False,
        label="Allow messages after move-out",
        help_text=(
            "Let RHP and the named former tenant send messages in this conversation. "
            "A reason is required. This does not reactivate the lease or financial account."
        ),
    )
    reason = forms.CharField(
        required=False, widget=forms.Textarea, label="Reason for allowing messages after move-out"
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, actor=actor, **kwargs)
        self.fields["lease"].widget = forms.HiddenInput()
        raw = (self.data if self.is_bound else self.initial).get("lease")
        if str(raw).isascii() and str(raw).isdecimal() and len(str(raw)) <= 19:
            self.fields["tenant"].queryset = (
                User.objects.filter(role=Role.TENANT)
                .filter(
                    Q(lease_memberships__lease_id=raw) | Q(participant__conversation__lease_id=raw)
                )
                .distinct()
            )
        if actor.is_tenant:
            for name in ("tenant", "followup", "reason"):
                self.fields.pop(name)
        self.fields["visibility"].help_text = (
            "Private means one named tenant and RHP staff. "
            "Shared includes the named co-tenants shown in the next step."
        )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFiles(forms.FileField):
    def clean(self, data, initial=None):
        return [super(MultipleFiles, self).clean(item) for item in (data or [])]


class MessageForm(StyledForm):
    body = forms.CharField(
        required=False,
        max_length=10000,
        widget=forms.Textarea(
            attrs={
                "rows": 1,
                "class": "chat-input",
                "placeholder": "Write a message…",
                "aria-label": "Message",
                "data-chat-input": "",
            }
        ),
        label="Message",
    )
    files = MultipleFiles(
        required=False,
        widget=MultipleFileInput(
            attrs={"accept": ".jpg,.jpeg,.png,.webp,.pdf", "class": "chat-file"}
        ),
        label="Attachments",
        help_text=(
            "Up to ten JPEG, PNG, WebP or PDF files within the portal upload limit. "
            "Re-select files after a validation error."
        ),
    )
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def clean(self):
        data = super().clean()
        if not data.get("body", "").strip() and not data.get("files"):
            raise forms.ValidationError("Enter a message or attach a file.")
        return data


class NoticeContentForm(StyledForm):
    title = forms.CharField(max_length=160)
    body = forms.CharField(max_length=10000, widget=forms.Textarea, label="Announcement")
    important = forms.BooleanField(required=False, label="Important — email eligible recipients")
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        label="Expires at",
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Reason for correction (shown in the announcement history)",
    )

    def __init__(self, *args, correction=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expires_at"].help_text = (
            f"Portal timezone: {timezone.get_current_timezone_name()}. "
            "Leave blank for no expiration."
        )
        if correction:
            self.fields["reason"].required = True
        else:
            self.fields.pop("reason")


class DraftForm(NoticeContentForm):
    properties = forms.ModelMultipleChoiceField(
        queryset=Property.objects.all(),
        required=False,
        label="Properties",
        help_text="Select one or more properties, or leave empty for all current tenancies.",
    )


class ActionForm(StyledForm):
    reason = forms.CharField(required=False, widget=forms.Textarea, max_length=2000, label="Reason")
    acknowledge_duplicate = forms.BooleanField(
        required=False,
        label="I understand that retrying an uncertain delivery may send a duplicate email.",
    )


class WorkForm(ActionForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("acknowledge_duplicate")


class QuickReplyForm(StyledModelForm):
    class Meta:
        model = QuickReply
        fields = ("label", "body", "property")
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}
        labels = {"body": "Message body", "property": "Property scope"}
        help_texts = {"property": "Leave blank to make the reply available across the portfolio."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = Property.objects.order_by("name")


class InternalNoteForm(StyledForm):
    body = forms.CharField(
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Internal note",
        help_text="Staff-only. Never visible to the tenant, emailed, or exported to them.",
    )
