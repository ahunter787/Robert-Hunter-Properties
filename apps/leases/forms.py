"""Forms for the lease screens."""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.common.forms import StyledForm, StyledModelForm
from apps.contacts.models import Person
from apps.leases.models import (
    STEPPING_TEMPLATES,
    EndReason,
    Lease,
    LeaseStatus,
    LeaseTemplate,
    LeaseTenant,
    RentPeriod,
)
from apps.properties.models import Unit


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
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "monthly_rent": "Rent at the start of the term",
            "template": "Lease template",
            "carries_nnn": "The tenant pays NNN on top of rent",
        }
        help_texts = {
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

        # The agreed deposit cannot be edited below the money RHP already holds for it
        # (ADR-028 D5): return or retain the held money first, then record the new term.
        if self.instance.pk:
            from apps.ledger import deposits

            held = deposits.held(self.instance)
            deposit = cleaned.get("deposit")
            if deposit is not None and deposit < held:
                self.add_error(
                    "deposit",
                    f"{held} is already held for this tenancy. Record the return or retention "
                    "first, then change the agreed amount.",
                )

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


class LeaseTenantForm(StyledModelForm):
    """One person on a lease: their role, and whether they are the primary contact."""

    class Meta:
        model = LeaseTenant
        fields = ["person", "role", "is_primary"]
        labels = {"is_primary": "Primary contact", "person": "Person"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = Person.objects.all().order_by(
            "last_name", "first_name", "pk"
        )
        self.fields["person"].empty_label = "Select a person"


class BaseLeaseTenantFormSet(forms.BaseInlineFormSet):
    """A lease needs at least one person, and at most one primary contact."""

    def clean(self):
        # These checks run before Django's own duplicate detection, which would
        # otherwise answer with "Please correct the duplicate data for tenant."
        # Django cleans every row before it calls this, so cleaned_data is ready.
        if any(self.errors):
            return

        people = []
        primaries = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            person = form.cleaned_data.get("person")
            if person is None:
                continue
            people.append(person)
            if form.cleaned_data.get("is_primary"):
                primaries += 1

        if not people:
            raise ValidationError("A lease needs at least one person.")
        if len(set(people)) != len(people):
            raise ValidationError("The same person is listed more than once.")
        if primaries > 1:
            raise ValidationError("Only one person can be the primary contact.")

        # Only now let Django check the database's own uniqueness rules, whose
        # per-row wording is for developers.
        super().clean()


LeaseTenantFormSet = inlineformset_factory(
    Lease,
    LeaseTenant,
    form=LeaseTenantForm,
    formset=BaseLeaseTenantFormSet,
    fields=["person", "role", "is_primary"],
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


# --- ending a tenancy (P4-Q1, P4-Q2) ---------------------------------------


class ExistingHistoryForm(StyledForm):
    billing_start_date = forms.DateField(
        label="Billing start date",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Where future posting checks begin. Existing records before this date remain.",
    )
    reason = forms.CharField(
        max_length=200,
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Explain why this date matches the account records you reviewed.",
    )


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
    forwarding_address = forms.CharField(
        max_length=500,
        required=False,
        label="Forwarding address (optional)",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=(
            "Where the final statement and any deposit refund are sent. It can be added or "
            "changed later on the move-out statement."
        ),
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
