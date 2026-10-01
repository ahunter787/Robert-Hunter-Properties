"""Forms for the lease screens."""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory

from apps.accounts.models import Role, User
from apps.common.forms import StyledModelForm
from apps.leases.models import Lease, LeaseStatus, LeaseTenant
from apps.properties.models import Unit

#: What a signed lease may be uploaded as.
LEASE_DOCUMENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})


class LeaseForm(StyledModelForm):
    class Meta:
        model = Lease
        fields = [
            "unit",
            "start_date",
            "end_date",
            "monthly_rent",
            "deposit",
            "rent_due_day",
            "lease_file",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"lease_file": "Lease document"}
        help_texts = {
            "lease_file": "The signed lease as a PDF, or a JPEG or PNG scan.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        free_units = (
            Unit.objects.select_related("property")
            .filter(is_active=True)
            .exclude(pk__in=Lease.objects.active().values("unit_id"))
        )
        if self.instance.pk:
            # Editing: keep its own unit selectable even if the unit is otherwise
            # taken, and freeze it once the lease is no longer a draft.
            free_units = Unit.objects.select_related("property").filter(
                Q(pk__in=free_units.values("pk")) | Q(pk=self.instance.unit_id)
            )
            if self.instance.status != LeaseStatus.DRAFT:
                self.fields["unit"].disabled = True
        self.fields["unit"].queryset = free_units.distinct().order_by(
            "property__name", "identifier"
        )
        self.fields["unit"].empty_label = "Select a unit"

    def clean(self):
        cleaned = super().clean()

        start_date, end_date = cleaned.get("start_date"), cleaned.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "A lease cannot end before it starts.")

        if self.instance.pk and self.instance.status != LeaseStatus.DRAFT:
            # The unit field is disabled, so Django ignores what was posted and
            # hands back the stored unit. Read the raw value instead: a tampered
            # POST is refused out loud rather than silently discarded.
            posted = self.data.get(self.add_prefix("unit"))
            if posted and str(posted) != str(self.instance.unit_id):
                self.add_error(
                    "unit",
                    "The unit cannot change once a lease has been activated. End this lease "
                    "and create a new one instead.",
                )
        return cleaned

    def clean_lease_file(self):
        document = self.cleaned_data.get("lease_file")
        # No content_type means the field still holds the stored file rather than
        # a fresh upload; Django has already validated that one.
        if not document or not hasattr(document, "content_type"):
            return document

        if document.size > settings.RHP_MAX_UPLOAD_MB * 1024 * 1024:
            raise ValidationError(
                f"That file is larger than {settings.RHP_MAX_UPLOAD_MB} MB. "
                "Compress it and try again."
            )
        if document.content_type not in LEASE_DOCUMENT_TYPES:
            raise ValidationError("Upload the lease as a PDF, or as a JPEG or PNG scan.")
        return document


class LeaseTenantForm(StyledModelForm):
    class Meta:
        model = LeaseTenant
        fields = ["tenant", "is_primary"]
        labels = {"is_primary": "Primary contact"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tenant"].queryset = User.objects.filter(
            role=Role.TENANT, is_active=True
        ).order_by("first_name", "last_name", "username")
        self.fields["tenant"].empty_label = "Select a tenant"


class BaseLeaseTenantFormSet(forms.BaseInlineFormSet):
    """A lease needs at least one tenant, and at most one primary contact."""

    def clean(self):
        # These checks run before Django's own duplicate detection, which would
        # otherwise answer with "Please correct the duplicate data for tenant."
        # Django cleans every row before it calls this, so cleaned_data is ready.
        if any(self.errors):
            return

        tenants = []
        primaries = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            tenant = form.cleaned_data.get("tenant")
            if tenant is None:
                continue
            tenants.append(tenant)
            if form.cleaned_data.get("is_primary"):
                primaries += 1

        if not tenants:
            raise ValidationError("A lease needs at least one tenant.")
        if len(set(tenants)) != len(tenants):
            raise ValidationError("The same tenant is listed more than once.")
        if primaries > 1:
            raise ValidationError("Only one tenant can be the primary contact.")

        # Only now let Django check the database's own uniqueness rules, whose
        # per-row wording is for developers.
        super().clean()


LeaseTenantFormSet = inlineformset_factory(
    Lease,
    LeaseTenant,
    form=LeaseTenantForm,
    formset=BaseLeaseTenantFormSet,
    fields=["tenant", "is_primary"],
    extra=1,
    can_delete=True,
)
