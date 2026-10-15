"""Forms for the lease screens."""

from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.common.forms import StyledForm, StyledModelForm
from apps.leases.models import (
    STEPPING_TEMPLATES,
    EndReason,
    Lease,
    LeaseStatus,
    LeaseTemplate,
    LeaseTenant,
    OnboardingMethod,
    RentPeriod,
)
from apps.properties.models import Unit

#: What a signed lease may be uploaded as.
LEASE_DOCUMENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})


class LeaseDocumentInput(forms.ClearableFileInput):
    template_name = "components/lease_document_input.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if value and value.instance.pk:
            context["widget"]["document_name"] = value.instance.document_name
            context["widget"]["document_url"] = reverse(
                "leases:lease-document", args=[value.instance.pk]
            )
        return context


class LeaseForm(StyledModelForm):
    class Meta:
        model = Lease
        fields = [
            "unit",
            "start_date",
            "end_date",
            "monthly_rent",
            "template",
            "carries_nnn",
            "step_up_month",
            "step_up_percent",
            "step_up_amount",
            "deposit",
            "rent_due_day",
            "lease_file",
            "lease_document_name",
            "notes",
        ]
        widgets = {
            "lease_file": LeaseDocumentInput(),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "lease_file": "Lease document",
            "lease_document_name": "Document name",
            "monthly_rent": "Rent at the start of the term",
            "template": "Lease template",
            "carries_nnn": "The tenant pays NNN on top of rent",
        }
        help_texts = {
            "lease_file": "The signed lease as a PDF, or a JPEG or PNG scan.",
            "template": (
                "How the base rent is set: fixed is one rent for the term, step up rises once a "
                "year, triple net is a step up with NNN, and stated amounts are entered from the "
                "lease exactly as it writes them."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: Set when a template change made a posted step-up rule inapplicable.
        self.rule_cleared = False

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

        # Choosing the Triple net template is also a statement that the tenant pays
        # NNN, so record the term explicitly. It then survives a later change of rent
        # template — a stated lease can carry NNN just as a triple-net one does (E4).
        if cleaned.get("template") == LeaseTemplate.NNN:
            cleaned["carries_nnn"] = True

        # A lease is often moved from a rule to the amounts its paper names. The rule
        # fields are then still in the posted form, and the model refuses them — which
        # reads as "this lease cannot be saved" rather than "that rule no longer
        # applies" (the owner hit exactly this on RHP's own lease). Drop them, and let
        # the view say so: a stated lease's amounts are added on the lease page (E4).
        template = cleaned.get("template")
        if template and template not in STEPPING_TEMPLATES:
            stale = [
                field
                for field in ("step_up_month", "step_up_percent", "step_up_amount")
                if cleaned.get(field)
            ]
            if stale:
                for field in stale:
                    cleaned[field] = None
                self.rule_cleared = True

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


# --- E1: the rent schedule and the NNN amount ------------------------------


class RentPeriodForm(StyledModelForm):
    """One period's rent, set by hand when the lease states a particular figure.

    The date is not a field: it is what the period *is*, and changing it would
    move money between months.
    """

    class Meta:
        model = RentPeriod
        fields = ["amount", "note"]
        labels = {"amount": "Monthly rent", "note": "Why"}
        help_texts = {"note": "For example: rent agreed at this figure in the renewal."}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount < Decimal("0.01"):
            raise ValidationError("A rent amount must be at least one cent.")
        return amount


class NnnRateForm(StyledForm):
    """Stage the NNN amount that applies from a date.

    Robert works the year's NNN out each November; entering the next year's figure
    while this one is still running is the normal case, so the date defaults to the
    next NNN year.
    """

    effective_from = forms.DateField(
        label="Applies from",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="A date rent falls due on. Rent due on a different day is refused.",
    )
    monthly_amount = forms.DecimalField(
        label="NNN a month",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        help_text="Enter 0 to suspend NNN from that date.",
    )
    note = forms.CharField(
        label="Note",
        max_length=200,
        required=False,
        help_text="Where the figure came from: the November calculation, a reconciliation.",
    )


class RentPeriodCreateForm(StyledForm):
    """A dated rent amount the lease states — a mid-term step, an extra space, a renewal."""

    effective_from = forms.DateField(
        label="From",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="A date rent falls due on, inside the tenancy.",
    )
    amount = forms.DecimalField(
        label="Monthly rent", max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    note = forms.CharField(
        max_length=200,
        required=False,
        help_text="What changed: 'extra space', 'renewal', 'agreed reduction'.",
    )


class OnboardingForm(StyledForm):
    """Place a tenancy that began before RHP: the history, or the position (E4)."""

    method = forms.ChoiceField(
        choices=OnboardingMethod.choices,
        initial=OnboardingMethod.HISTORY,
        label="How to record prior activity",
        help_text=(
            "Recreate charges from the lease start and record payments already received, or "
            "start from a date and enter an opening balance."
        ),
    )
    as_of = forms.DateField(
        label="Figures as of",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="The date the amounts below speak to.",
    )
    received_total = forms.DecimalField(
        label="Received before RHP",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        help_text="Everything the tenant has paid to date. It settles the oldest months first.",
    )
    opening_amount = forms.DecimalField(
        label="Opening balance",
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text=(
            "Positive if the tenant owes, negative for a credit balance, or 0 if paid in full."
        ),
    )
    billing_start_date = forms.DateField(
        label="Bill from",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        help_text="The first month RHP posts charges for. Leave blank to use the whole term.",
    )
    note = forms.CharField(max_length=200, required=False, help_text="Where the figures came from.")

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method")
        if method == OnboardingMethod.HISTORY and cleaned.get("received_total") is None:
            self.add_error(
                "received_total", "Say what the tenant had paid before RHP (0 if nothing)."
            )
        if method == OnboardingMethod.POSITION:
            if cleaned.get("opening_amount") is None:
                self.add_error("opening_amount", "Enter 0 if the account was paid in full.")
            if not cleaned.get("billing_start_date"):
                self.add_error("billing_start_date", "Say which month RHP starts billing from.")
        return cleaned


# --- ending a tenancy (P4-Q1, P4-Q2) ---------------------------------------


class LeaseEndForm(StyledForm):
    """End a tenancy: when it stops, why, and what the close-out should cancel.

    The reason and its detail are required. Ending a tenancy is a decision somebody has to be
    able to cite later, and the office is the only place that knowledge exists.
    """

    ended_on = forms.DateField(
        label="Tenancy ends",
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={"required": "Say which day the tenancy stops."},
        help_text=(
            "The day the tenancy actually stops. The term the lease was signed for is kept "
            "as it is, so ending early is recorded rather than rewritten."
        ),
    )
    reason = forms.ChoiceField(
        choices=EndReason.choices,
        label="Why it is ending",
        error_messages={"required": "Say why the tenancy is ending."},
        help_text="Citable: this appears on the tenancy, in its history and in reports.",
    )
    note = forms.CharField(
        max_length=200,
        label="The detail",
        error_messages={"required": "Add the detail behind the reason."},
        help_text="Who asked, what was agreed, what was served. Two or three sentences.",
    )

    def __init__(self, *args, lease=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lease = lease
        if lease is not None and not self.is_bound:
            self.fields["ended_on"].initial = timezone.localdate()


class LeaseSettleForm(StyledForm):
    """Close a tenancy's money for good. A note for the record, nothing else."""

    note = forms.CharField(
        max_length=200,
        required=False,
        label="For the record",
        help_text="Optional: how the last of it was dealt with.",
    )


class LeaseReopenForm(StyledForm):
    """Put an ended tenancy back on, so a debt found later can be billed honestly."""

    reason = forms.CharField(
        max_length=200,
        label="Why it is being reopened",
        help_text="What was found after the tenancy ended, and why it has to be billed now.",
    )
