from django import forms
from django.utils import timezone

from apps.common.forms import StyledForm
from apps.documents.models import Document

from .models import EntryKind


class ManualEntryForm(StyledForm):
    kind = forms.ChoiceField(choices=EntryKind.choices, initial=EntryKind.NOTE)
    body = forms.CharField(max_length=10000, widget=forms.Textarea(attrs={"rows": 4}))
    occurred_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    visible_to_tenant = forms.BooleanField(
        required=False,
        label="Share with the tenant",
        help_text="The tenant sees this manual entry, never internal-only notes.",
    )
    document = forms.ModelChoiceField(
        queryset=Document.objects.none(), required=False, label="Attachment (optional)"
    )

    def __init__(self, *args, lease, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document"].queryset = Document.objects.filter(
            lease=lease, tenant_visible=False
        ).order_by("-created_at")
