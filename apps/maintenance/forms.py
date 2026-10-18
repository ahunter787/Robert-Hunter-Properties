"""Plain forms: every workflow remains usable without JavaScript."""

from decimal import Decimal

from django import forms
from django.urls import reverse
from django.utils.formats import date_format

from apps.accounts.models import STAFF_ROLES, User
from apps.leases.models import Lease
from apps.properties.models import Property, Unit

from .models import CATEGORIES, Audience, Cost, Priority, Status, Vendor
from .services import eligible_leases


class LeaseChoice(forms.ModelChoiceField):
    def label_from_instance(self, lease):
        return (
            f"{lease.unit.label} · {lease.tenant_names} · "
            f"{date_format(lease.start_date, 'M j, Y')}–{date_format(lease.end_date, 'M j, Y')}"
        )


class AudienceChoice(LeaseChoice):
    def label_from_instance(self, audience):
        return super().label_from_instance(audience.lease)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        return [
            super(MultipleFileField, self).clean(item, initial)
            for item in (data if isinstance(data, list) else [data])
        ]


class UploadForm(forms.Form):
    files = MultipleFileField(
        label="Photos",
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        help_text="Up to ten JPEG, PNG, or WebP photos. Maximum 5 MB each.",
    )


ENTRY_AUTHORIZATION = (
    "I give RHP staff and its assigned repair professionals permission to enter my unit "
    "for this request."
)


class LocationForm(forms.Form):
    property = forms.ModelChoiceField(queryset=Property.objects.all())
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(), required=False, empty_label="Property-wide request"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        property_id = (self.data if self.is_bound else self.initial).get("property")
        if str(property_id).isdigit():
            self.fields["unit"].queryset = Unit.objects.filter(property_id=property_id)
        self.fields["property"].widget.attrs.update(
            {
                "hx-get": reverse("maintenance:units"),
                "hx-target": "#id_unit",
                "hx-swap": "innerHTML",
                "hx-sync": "this:replace",
                "hx-trigger": "change",
            }
        )


class RequestForm(UploadForm):
    field_order = [
        "lease",
        "property",
        "unit",
        "location",
        "category",
        "title",
        "description",
        "permission",
        "files",
    ]
    title = forms.CharField(max_length=200)
    category = forms.ChoiceField(choices=CATEGORIES)
    description = forms.CharField(widget=forms.Textarea)
    lease = LeaseChoice(queryset=Lease.objects.none(), label="Your tenancy", required=False)
    location = forms.ChoiceField(
        choices=[("unit", "My unit"), ("property", "Shared property area")], required=False
    )
    property = forms.ModelChoiceField(queryset=Property.objects.all(), required=False)
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(), required=False, empty_label="Property-wide request"
    )
    permission = forms.BooleanField(label=ENTRY_AUTHORIZATION, required=False, initial=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if actor.is_tenant:
            self.fields["lease"].queryset = Lease.objects.current().for_tenant(actor)
            self.fields["lease"].required = True
            self.fields["location"].required = True
            del self.fields["property"], self.fields["unit"]
        else:
            del self.fields["lease"], self.fields["location"], self.fields["permission"]
            self.fields["property"].required = True
            property_id = (self.data if self.is_bound else self.initial).get("property")
            if str(property_id).isdigit():
                self.fields["unit"].queryset = Unit.objects.filter(property_id=property_id)
            self.fields["property"].widget = forms.HiddenInput()
            self.fields["unit"].widget = forms.HiddenInput()


class UpdateForm(UploadForm):
    field_order = ["audience", "body", "files"]
    body = forms.CharField(label="Update", widget=forms.Textarea)
    audience = AudienceChoice(
        queryset=Audience.objects.none(),
        required=False,
        empty_label="Internal note — staff only",
        label="Who can see this update?",
    )

    def __init__(self, *args, request, actor, **kwargs):
        super().__init__(*args, **kwargs)
        rows = request.audiences.select_related("lease__unit__property")
        if actor.is_tenant:
            rows = rows.filter(
                lease__lease_tenants__tenant=actor, lease__in=Lease.objects.current()
            ).distinct()
            self.fields["audience"].required = True
            self.fields["audience"].label = "Your tenancy"
            self.fields["audience"].empty_label = None
        self.fields["audience"].queryset = rows


class EditForm(forms.Form):
    body = forms.CharField(label="Corrected update", widget=forms.Textarea)
    reason = forms.CharField(
        widget=forms.Textarea,
        help_text="The previous text and your reason will be retained for staff review.",
    )


class ShareForm(forms.Form):
    lease = LeaseChoice(queryset=Lease.objects.none(), label="Share with tenancy")
    introduction = forms.CharField(
        widget=forms.Textarea,
        help_text="Only this message is shared. Existing private conversations stay private.",
    )

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        rows = Lease.objects.current().filter(unit__property_id=request.property_id)
        if request.unit_id:
            rows = rows.filter(unit_id=request.unit_id)
        self.fields["lease"].queryset = rows.exclude(pk__in=request.audiences.values("lease_id"))


class PublishForm(forms.Form):
    audience = AudienceChoice(queryset=Audience.objects.none(), label="Publish a separate copy to")
    confirm = forms.BooleanField(
        label="Publish this internal note to the selected tenancy. Attachments are not copied."
    )

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["audience"].queryset = request.audiences.select_related("lease__unit__property")


class WorkForm(forms.Form):
    status = forms.ChoiceField(choices=Status.choices)
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Required for waiting, reopening, or moving work backward.",
    )
    priority = forms.TypedChoiceField(choices=Priority.choices, coerce=int)
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True, role__in=STAFF_ROLES), required=False
    )
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.all(), required=False)
    scheduled_for = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        label="Scheduled date and time",
    )
    schedule_window = forms.CharField(
        max_length=100,
        required=False,
        help_text=(
            "For example, Oct 20, 2026, 9 AM–noon. Enter a date/time above or a time window here."
        ),
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if not actor.is_manager_or_above:
            selected = self.initial.get("assigned_to")
            self.fields["assigned_to"].queryset = User.objects.filter(
                pk=selected.pk if selected else None
            )
            selected_vendor = self.initial.get("vendor")
            self.fields["vendor"].queryset = Vendor.objects.filter(
                pk=selected_vendor.pk if selected_vendor else None
            )
            self.fields["status"].choices = [
                (s, Status(s).label) for s in (Status.IN_PROGRESS, Status.WAITING, Status.COMPLETED)
            ]
            for name in ("priority", "assigned_to", "vendor", "scheduled_for", "schedule_window"):
                self.fields[name].disabled = True


class PermissionForm(forms.Form):
    audience = AudienceChoice(queryset=Audience.objects.none(), label="Tenancy")
    permission = forms.BooleanField(label=ENTRY_AUTHORIZATION, required=False, initial=False)
    source_note = forms.CharField(
        label="How was this authorization or withdrawal received?",
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="For example, tenant called today. Staff only; not shown to tenants or emailed.",
    )

    def __init__(self, *args, request, actor, audience_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        rows = request.audiences.select_related("lease__unit__property")
        if actor.is_tenant:
            rows = rows.filter(
                lease__lease_tenants__tenant=actor, lease__in=Lease.objects.current()
            ).distinct()
        self.fields["audience"].queryset = rows
        self.fields["audience"].widget = forms.HiddenInput()
        if actor.is_tenant:
            del self.fields["source_note"]
        else:
            self.fields["permission"].label = (
                "Tenant has authorized RHP staff and assigned repair professionals to enter "
                "for this request."
            )
        if self.is_bound:
            audience_id = self.data.get("audience")
        self.selected_audience = (
            rows.filter(pk=audience_id).first() if str(audience_id).isdigit() else None
        )
        if audience_id is None:
            self.selected_audience = rows.first()
        if self.selected_audience and not self.is_bound:
            self.initial.update(
                audience=self.selected_audience.pk,
                permission=self.selected_audience.permission_to_enter,
            )


class CostForm(UploadForm):
    field_order = [
        "corrects",
        "direction",
        "amount",
        "description",
        "incurred_on",
        "vendor",
        "reference",
        "reason",
        "files",
    ]
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    description = forms.CharField(max_length=255)
    incurred_on = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Expense date"
    )
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.all(), required=False)
    reference = forms.CharField(max_length=200, required=False)
    corrects = forms.ModelChoiceField(
        queryset=Cost.objects.none(),
        required=False,
        label="Corrects expense",
        empty_label="New expense",
    )
    direction = forms.ChoiceField(
        label="Expense or correction type",
        choices=[("INCREASE", "Expense / increase"), ("DECREASE", "Reduction")],
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Required for a correction. Original expenses cannot be overwritten.",
    )

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["corrects"].queryset = request.costs.filter(corrects__isnull=True)
        self.fields["files"].widget.attrs["accept"] += ",application/pdf"
        self.fields["files"].label = "Invoices or receipts"
        self.fields["files"].help_text = (
            "Up to ten photos or PDF invoices/receipts; 5 MB each. "
            "Only managers can view these files."
        )


class AllocationForm(forms.Form):
    lease = LeaseChoice(queryset=Lease.objects.none(), label="Tenancy")
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    due = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Due date")
    reason = forms.CharField(max_length=240, label="Reason for tenant charge")

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lease"].queryset = eligible_leases(request)


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ("name", "contact", "trades", "is_active")


class RemovalForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea)
    confirm = forms.BooleanField(
        label="Remove the file. Its name, removal reason, and audit history will be retained."
    )
