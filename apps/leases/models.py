"""Lease models: the record that connects a unit to the people renting it.

Phase 3. A lease state is explicit — staff activate and end it — rather than being
inferred from dates, because a signed lease that has not started yet must never
look active. "One active lease per unit" is a database constraint, not a
convention (ADR-007).
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.dates import due_date_in, ordinal
from apps.properties.models import Unit

#: A zero amount, for the NNN that has not been staged yet.
ZERO = Decimal("0.00")


def lease_document_path(instance, filename: str) -> str:
    """Randomised storage path: never the client's filename (docs/security.md)."""
    if not instance.lease_document_name:
        instance.lease_document_name = Path(filename.replace("\\", "/")).name[:255]
    suffix = Path(filename).suffix.lower()
    if len(suffix) > 10 or not suffix.isascii():
        suffix = ""
    return f"lease_documents/{uuid4().hex}{suffix}"


class LeaseStatus(models.TextChoices):
    """The occupancy lifecycle of a tenancy."""

    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ENDED = "ENDED", "Ended"


class LeaseAccountStatus(models.TextChoices):
    """Whether an ended tenancy's financial account can still change."""

    OPEN = "OPEN", "Open"
    SETTLED = "SETTLED", "Settled"


class EndReason(models.TextChoices):
    """Why a tenancy ended. A citable reason is required on every ending (P4-Q1)."""

    TENANT_EARLY = "TENANT_EARLY", "Tenant ended early"
    END_OF_TERM = "END_OF_TERM", "End of term, not renewed"
    EVICTION = "EVICTION", "Eviction"
    SALE = "SALE", "Property sold or transferred"
    MUTUAL = "MUTUAL", "By mutual agreement"
    OTHER = "OTHER", "Other"


class LeaseTemplate(models.TextChoices):
    """The shapes an RHP lease takes (E1, ADR-013; STATED arrives with E4).

    A *stated* lease is one whose paper names each amount — a mid-term step, an
    "extra space" change, a renegotiation — instead of a rule the term follows.
    The office enters those dates and figures; RHP never invents one.
    """

    FIXED = "FIXED", "Fixed"
    STEP_UP = "STEP_UP", "Step up"
    NNN = "NNN", "Triple net (NNN)"
    STATED = "STATED", "The lease states the amounts"


class RentPeriodOrigin(models.TextChoices):
    """Where a period's amount came from, so the screen can say why it is what it is."""

    BASE = "BASE", "Starting rent"
    STEP_UP = "STEP_UP", "Step up"
    MANUAL = "MANUAL", "Override amount"


#: The templates that carry a once-a-year step up.
STEPPING_TEMPLATES = (LeaseTemplate.STEP_UP, LeaseTemplate.NNN)

#: The templates whose rent comes from dated periods at all.
SCHEDULED_TEMPLATES = (LeaseTemplate.STEP_UP, LeaseTemplate.NNN, LeaseTemplate.STATED)


class OnboardingMethod(models.TextChoices):
    """How a live tenancy that began before RHP was brought in (E4)."""

    HISTORY = "HISTORY", "Recreate charges from the lease start"
    POSITION = "POSITION", "Enter an opening balance"


class LeaseQuerySet(models.QuerySet):
    """The lease questions the rest of the application asks, answered in one place."""

    def active(self):
        return self.filter(status=LeaseStatus.ACTIVE)

    def current(self, on_date=None):
        """Active leases whose term covers the given day (today by default).

        This is RHP's single definition of occupancy: a draft, a lease that has
        not started, and an ended lease all leave the unit unoccupied.
        """
        day = on_date or timezone.localdate()
        return self.active().filter(start_date__lte=day, end_date__gte=day)

    def expiring_within(self, days: int):
        """Active leases ending in the next ``days`` days, soonest first."""
        day = timezone.localdate()
        return self.active().filter(end_date__gte=day, end_date__lte=day + dt.timedelta(days=days))

    def for_tenant(self, user):
        return self.filter(lease_tenants__tenant=user).distinct()

    def visible_for(self, user):
        """The one lease a tenant should see: the current one, otherwise the latest.

        A draft is the office's working copy — its rent and term can still change —
        so a tenant never sees one. They see nothing until the tenancy is
        activated, and the screens say so rather than showing terms that may not
        be agreed.

        This is the single lookup behind every tenant-facing page, so a tenant can
        only ever be shown a lease they are actually on.
        """
        leases = (
            self.for_tenant(user)
            .exclude(status=LeaseStatus.DRAFT)
            .select_related("unit__property")
            .prefetch_related("lease_tenants__tenant")
        )
        current = leases.current().first()
        if current is not None:
            return current
        return leases.order_by("-end_date", "-start_date").first()


class Lease(models.Model):
    """A tenancy: a term, a rent, and the people on it, for one unit."""

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Rent per month at the start of the term, in dollars.",
    )
    template = models.CharField(
        max_length=10,
        choices=LeaseTemplate.choices,
        default=LeaseTemplate.FIXED,
        help_text=(
            "How the base rent is set: fixed, a once-a-year step up, triple-net (NNN), or "
            "amounts stated in the lease."
        ),
    )
    carries_nnn = models.BooleanField(
        default=False,
        help_text=(
            "The lease passes the property's operating costs to the tenant on top of rent. "
            "This can apply to any rent template."
        ),
    )
    step_up_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month the rent steps up, for a step-up or triple-net lease.",
    )
    step_up_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Yearly increase as a percentage: 7 means 7%.",
    )
    step_up_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Yearly increase as a fixed amount, when the lease states one instead.",
    )
    billing_start_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "The first month RHP posts charges for. Leave blank to start with the lease term."
        ),
    )
    deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Security deposit held, in dollars. Zero if none.",
    )
    rent_due_day = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day of the month rent is due. A shorter month uses its last day.",
    )
    status = models.CharField(
        max_length=10,
        choices=LeaseStatus.choices,
        default=LeaseStatus.DRAFT,
        db_index=True,
        help_text="Draft until staff activate it; ended is history and read-only.",
    )
    account_status = models.CharField(
        max_length=10,
        choices=LeaseAccountStatus.choices,
        default=LeaseAccountStatus.OPEN,
        db_index=True,
        help_text="Open while financial work remains; settled when the ended account is complete.",
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settled_lease_accounts",
    )
    settlement_note = models.CharField(max_length=200, blank=True)
    ended_on = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "The day the tenancy actually stopped. `end_date` stays the term the agreement "
            "was signed for, so ending early is recorded rather than rewritten (P4-Q1)."
        ),
    )
    end_reason = models.CharField(
        max_length=16,
        choices=EndReason.choices,
        blank=True,
        help_text="Why the tenancy ended. Citable, so it is shown on the tenancy and in reports.",
    )
    end_reason_note = models.CharField(
        max_length=200,
        blank=True,
        help_text="The detail behind the reason: who asked, what was agreed, what was served.",
    )
    lease_file = models.FileField(
        upload_to=lease_document_path,
        blank=True,
        null=True,
        help_text="The signed lease as a PDF or scan.",
    )
    lease_document_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="A readable document name. Leave blank to use the uploaded filename.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LeaseQuerySet.as_manager()

    class Meta:
        ordering = ("-start_date", "unit__property__name", "unit__identifier")
        constraints = [
            # The rule that stops a unit being rented twice.
            models.UniqueConstraint(
                fields=["unit"],
                condition=models.Q(status=LeaseStatus.ACTIVE),
                name="one_active_lease_per_unit",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="lease_ends_on_or_after_it_starts",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(account_status=LeaseAccountStatus.OPEN)
                    | (
                        models.Q(account_status=LeaseAccountStatus.SETTLED)
                        & models.Q(status=LeaseStatus.ENDED)
                        & models.Q(settled_at__isnull=False)
                    )
                ),
                name="settled_account_requires_ended_lease",
            ),
        ]
        indexes = [models.Index(fields=["status", "end_date"], name="lease_status_end")]

    def __str__(self) -> str:
        return f"{self.unit.label} ({self.start_date} to {self.end_date})"

    def save(self, *args, **kwargs):
        # The Triple net template *is* a statement that the tenant pays NNN, so record
        # the term whenever that template is saved, whichever path got here (the form
        # does it too). Without this a lease created outside the form would read as
        # triple net while the flag said otherwise, and moving it to the stated
        # template would quietly drop NNN (E4).
        if self.template == LeaseTemplate.NNN:
            self.carries_nnn = True
        return super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        return self.unit.label

    @property
    def document_name(self) -> str:
        """Display metadata independent of the private storage path."""
        return self.lease_document_name or "Signed lease"

    @property
    def is_current(self) -> bool:
        today = timezone.localdate()
        return self.status == LeaseStatus.ACTIVE and self.start_date <= today <= self.end_date

    @property
    def has_started(self) -> bool:
        return self.start_date <= timezone.localdate()

    @property
    def has_ended(self) -> bool:
        return self.end_date < timezone.localdate()

    @property
    def is_editable(self) -> bool:
        """An ended tenancy is history: kept, readable, and not rewritten."""
        return self.status != LeaseStatus.ENDED

    @property
    def is_ended(self) -> bool:
        """Post-tenancy: the tenancy has stopped and its money is still open (P4-Q1)."""
        return self.status == LeaseStatus.ENDED

    @property
    def is_settled(self) -> bool:
        """The financial account is closed against further changes."""
        return self.account_status == LeaseAccountStatus.SETTLED

    @property
    def stopped_on(self) -> dt.date:
        """When the tenancy stopped: the day recorded, or the term it ran to.

        A tenancy ended before RHP recorded end dates has only its term, and that is what the
        screens show for it — `end_reason` being blank is how a reader can tell that nobody
        wrote down why. Never `None`: every ended tenancy stopped on *some* day.
        """
        return self.ended_on or self.end_date

    @property
    def ended_early(self) -> bool:
        """Whether the tenancy stopped before the term it was signed for."""
        return bool(self.ended_on and self.ended_on < self.end_date)

    @property
    def can_be_charged(self) -> bool:
        """Whether a new obligation may be raised on this tenancy.

        Only a running tenancy takes charges (P4-Q1, P4-Q3). This is the single rule the
        services consult — see `apps.ledger.services.generate_charges` — and the one place
        the post-tenancy work (P4-E6) will relax, deliberately, once a charge can carry its
        evidence from Phase 6.
        """
        return self.status == LeaseStatus.ACTIVE

    @property
    def due_day_label(self) -> str:
        return f"{ordinal(self.rent_due_day)} of every month"

    def clean(self):
        """The template decides which step-up fields are required (E1, ADR-013)."""
        super().clean()
        if self.template not in STEPPING_TEMPLATES:
            if any((self.step_up_month, self.step_up_percent, self.step_up_amount)):
                raise ValidationError(
                    {
                        "template": (
                            "This lease template has no step-up rule. Clear the step-up month "
                            "and increase, or choose Step up or Triple net to record one."
                        )
                    }
                )
            return

        errors = {}
        if self.step_up_month is None:
            errors["step_up_month"] = "Say which month the rent steps up in."
        if (self.step_up_percent is None) == (self.step_up_amount is None):
            errors["step_up_percent"] = (
                "Give the yearly increase as either a percentage or a fixed amount, not both."
            )
        if errors:
            raise ValidationError(errors)

    # --- what this lease charges ------------------------------------------
    # Callers ask the lease, never the stored field, so a stepped lease answers
    # per period and a fixed one answers with the same figure for the whole term.
    # A lease with no periods is exactly the fixed case (ADR-013).

    @property
    def uses_schedule(self) -> bool:
        """Whether this lease's rent comes from dated amounts at all (E1, E4)."""
        return self.template in SCHEDULED_TEMPLATES

    @property
    def is_stated(self) -> bool:
        """A lease whose paper names each amount, so RHP never invents one (E4)."""
        return self.template == LeaseTemplate.STATED

    @property
    def uses_nnn(self) -> bool:
        """Whether this lease charges NNN on top of rent (E1, E4).

        NNN is not a rent template, it is a term of the lease: the tenant pays their
        share of the property's operating costs. The Triple net template is the common
        case — a step-up rent *and* NNN — but a lease that states its own rent can carry
        NNN too, and that is exactly what RHP's own lease does (ADR-016).
        """
        return self.carries_nnn or self.template == LeaseTemplate.NNN

    @property
    def template_label(self) -> str:
        """The rent template as a reader should see it, naming NNN when it is separate."""
        label = self.get_template_display()
        if self.carries_nnn and self.template != LeaseTemplate.NNN:
            return f"{label} + NNN"
        return label

    # --- bringing a live tenancy in (E4) ----------------------------------

    @property
    def bill_from(self) -> dt.date:
        """The first month RHP charges for: the cutover, or the start of the term."""
        return self.billing_start_date or self.start_date

    @property
    def is_retroactive(self) -> bool:
        """A tenancy whose term began before this month: it has a history to place."""
        return self.start_date < timezone.localdate().replace(day=1)

    @property
    def onboarding_record(self) -> LeaseOnboarding | None:
        """How this tenancy was brought in, if it has been (E4)."""
        if not self.pk:
            return None
        return LeaseOnboarding.objects.filter(lease_id=self.pk).first()

    @property
    def has_onboarding(self) -> bool:
        """Whether the opening position has been recorded at all (E4)."""
        return self.onboarding_record is not None

    @property
    def needs_onboarding(self) -> bool:
        """A live tenancy from before RHP that nobody has placed yet.

        While this is true no charges may be raised: the generator would bill the
        whole past as if it were new, which is the phantom debt E4 exists to make
        impossible (ADR-016). *Placing* the tenancy is what sets the cutover, and the
        cutover is what unlocks charging — the onboarding record says how it was
        placed, while the cutover says from when RHP bills.
        """
        return (
            self.status == LeaseStatus.ACTIVE
            and self.is_retroactive
            and self.billing_start_date is None
        )

    def _cached(self, attribute, queryset_name):
        """Read a related set once per instance; callers prefetch it in lists."""
        cache = getattr(self, attribute, None)
        if cache is None:
            cache = list(getattr(self, queryset_name).all())
            setattr(self, attribute, cache)
        return cache

    @property
    def rent_periods_ordered(self) -> list[RentPeriod]:
        periods = self._cached("_rent_period_cache", "rent_periods")
        return sorted(periods, key=lambda period: period.effective_from)

    @property
    def nnn_rates_ordered(self) -> list[NnnRate]:
        return sorted(self._cached("_nnn_rate_cache", "nnn_rates"), key=lambda r: r.effective_from)

    def rent_for(self, on_date) -> Decimal:
        """What this lease charges per month on a given date."""
        applicable = [p for p in self.rent_periods_ordered if p.effective_from <= on_date]
        if not applicable:
            return self.monthly_rent
        return applicable[-1].amount

    def nnn_for(self, on_date) -> Decimal:
        """The NNN amount that applied on a given date; zero when none is staged."""
        applicable = [r for r in self.nnn_rates_ordered if r.effective_from <= on_date]
        if not applicable:
            return ZERO
        return applicable[-1].monthly_amount

    @property
    def starting_rent(self) -> Decimal:
        """The rent the term opens with: the first period, or the stated rent."""
        periods = self.rent_periods_ordered
        return periods[0].amount if periods else self.monthly_rent

    @property
    def current_base_rent(self) -> Decimal:
        return self.rent_for(timezone.localdate())

    @property
    def current_nnn(self) -> Decimal:
        return self.nnn_for(timezone.localdate())

    @property
    def current_month_total(self) -> Decimal:
        """Rent plus NNN at today's figures: what a month costs before utilities."""
        return self.current_base_rent + self.current_nnn

    def next_rent_change(self, *, today=None) -> RentPeriod | None:
        """The next period whose amount starts after today, if there is one."""
        day = today or timezone.localdate()
        upcoming = [p for p in self.rent_periods_ordered if p.effective_from > day]
        return upcoming[0] if upcoming else None

    def next_nnn_change(self, *, today=None) -> NnnRate | None:
        day = today or timezone.localdate()
        upcoming = [r for r in self.nnn_rates_ordered if r.effective_from > day]
        return upcoming[0] if upcoming else None

    def current_nnn_rate(self, *, today=None) -> NnnRate | None:
        day = today or timezone.localdate()
        applicable = [r for r in self.nnn_rates_ordered if r.effective_from <= day]
        return applicable[-1] if applicable else None

    @property
    def tenants(self):
        """Everyone on the lease. Prefetch ``lease_tenants__tenant`` in lists."""
        return [link.tenant for link in self.lease_tenants.all()]

    @property
    def primary_tenant(self):
        for link in self.lease_tenants.all():
            if link.is_primary:
                return link.tenant
        return None

    @property
    def tenant_names(self) -> str:
        names = [tenant.display_name for tenant in self.tenants]
        return ", ".join(names) if names else "No tenants yet"


def _check_due_date(instance) -> None:
    """A date a lease's rent falls on: inside the term, on the due day.

    One rule, used by both the rent schedule and the NNN rates, so a value can
    never apply from the middle of a month (ADR-013).
    """
    if instance.lease_id is None or instance.effective_from is None:
        return
    lease = instance.lease
    due = instance.effective_from
    if not (lease.start_date <= due <= lease.end_date):
        raise ValidationError({"effective_from": "That date is outside this lease's term."})
    if due_date_in(due.year, due.month, lease.rent_due_day) != due:
        raise ValidationError(
            {
                "effective_from": (
                    f"Rent falls due on the {ordinal(lease.rent_due_day)} of the month; "
                    "use that date."
                )
            }
        )


class RentPeriod(models.Model):
    """The rent one lease charges from a date until the next period (E1).

    A lease with no periods is a fixed rent for its whole term: the stored
    ``monthly_rent``. Periods exist for a step-up or triple-net lease, where the
    term's amounts are worked out once and then left alone.
    """

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="rent_periods")
    effective_from = models.DateField(help_text="The rent due date this amount starts from.")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    origin = models.CharField(
        max_length=10, choices=RentPeriodOrigin.choices, default=RentPeriodOrigin.BASE
    )
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rent_periods_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("effective_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "effective_from"], name="one_rent_period_per_due_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.amount} from {self.effective_from}"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        _check_due_date(self)
        if self.lease_id is not None and self.lease.template not in SCHEDULED_TEMPLATES:
            raise ValidationError(
                {
                    "lease": (
                        "A fixed lease has one rent for its term. Make the lease a step up, "
                        "triple net or stated-amounts lease to record dated amounts."
                    )
                }
            )


class NnnRate(models.Model):
    """The NNN amount a triple-net lease carries from a date (E1).

    Robert works the year's NNN out each November and stages it: the rate in force
    keeps applying until the staged one's date arrives. A rate is a lease term, not
    a ledger entry, so it is corrected here — never by editing a charge.
    """

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="nnn_rates")
    effective_from = models.DateField(help_text="The rent due date this amount starts from.")
    monthly_amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    note = models.CharField(max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nnn_rates_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("effective_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "effective_from"], name="one_nnn_rate_per_due_date"
            )
        ]

    def __str__(self) -> str:
        return f"NNN {self.monthly_amount} from {self.effective_from}"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        _check_due_date(self)
        if self.lease_id is not None and not self.lease.uses_nnn:
            raise ValidationError({"lease": "Only a lease that carries NNN takes an NNN amount."})


class LeaseOnboarding(models.Model):
    """How a live tenancy that began before RHP was brought in (E4).

    One record per lease, written once, saying which of the two ways the tenancy
    was placed and what figures it was placed with. The money itself lives in the
    ledger — a brought-forward charge, a credit, or the payment that settled the
    history — so this table is the *decision*, and the ledger is the arithmetic.
    """

    lease = models.OneToOneField(Lease, on_delete=models.PROTECT, related_name="onboarding")
    method = models.CharField(max_length=10, choices=OnboardingMethod.choices)
    as_of = models.DateField(help_text="The date this position speaks to.")
    #: Method HISTORY: the total received from the tenant before RHP, as one figure.
    received_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Everything received before RHP, brought in as one settling payment.",
    )
    #: Method POSITION: what was owed at the cutover. Positive owed, negative in credit.
    opening_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Balance brought forward: positive owed, negative paid ahead.",
    )
    note = models.CharField(max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lease_onboardings_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "lease onboarding"

    def __str__(self) -> str:
        return f"{self.lease} · {self.get_method_display()}"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.method == OnboardingMethod.HISTORY and self.received_total is None:
            raise ValidationError({"received_total": "Say what the tenant had paid before RHP."})
        if self.method == OnboardingMethod.POSITION and self.opening_amount is None:
            raise ValidationError(
                {"opening_amount": "Enter 0 if the account was paid in full on that date."}
            )


class LeaseTenant(models.Model):
    """The specification's LEASE TENANT: who is on the lease, and who is primary."""

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="lease_tenants")
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # PROTECT: a person with tenancy history is never deleted.
        on_delete=models.PROTECT,
        related_name="lease_memberships",
        limit_choices_to={"role": "TENANT"},
    )
    is_primary = models.BooleanField(default=False, help_text="The primary contact for this lease.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_primary", "tenant__first_name", "tenant__last_name", "tenant__username")
        constraints = [
            models.UniqueConstraint(fields=["lease", "tenant"], name="tenant_once_per_lease"),
            models.UniqueConstraint(
                fields=["lease"],
                condition=models.Q(is_primary=True),
                name="one_primary_tenant_per_lease",
            ),
        ]

    def __str__(self) -> str:
        role = "primary tenant" if self.is_primary else "tenant"
        return f"{self.tenant.display_name} ({role} on {self.lease})"
