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
    suffix = Path(filename).suffix.lower()
    if len(suffix) > 10 or not suffix.isascii():
        suffix = ""
    return f"lease_documents/{uuid4().hex}{suffix}"


class LeaseStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ENDED = "ENDED", "Ended"


class LeaseTemplate(models.TextChoices):
    """The three shapes an RHP lease takes (E1, ADR-013)."""

    FIXED = "FIXED", "Fixed"
    STEP_UP = "STEP_UP", "Step up"
    NNN = "NNN", "Triple net (NNN)"


class RentPeriodOrigin(models.TextChoices):
    """Where a period's amount came from, so the screen can say why it is what it is."""

    BASE = "BASE", "Starting rent"
    STEP_UP = "STEP_UP", "Step up"
    MANUAL = "MANUAL", "Set by hand"


#: The templates that carry a once-a-year step up.
STEPPING_TEMPLATES = (LeaseTemplate.STEP_UP, LeaseTemplate.NNN)


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
            "Fixed, a once-a-year step up, or triple net — rent plus an NNN amount set each year."
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
    lease_file = models.FileField(
        upload_to=lease_document_path,
        blank=True,
        null=True,
        help_text="The signed lease, as a PDF or a scan. Later phases take over document handling.",
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
        ]
        indexes = [models.Index(fields=["status", "end_date"], name="lease_status_end")]

    def __str__(self) -> str:
        return f"{self.unit.label} ({self.start_date} to {self.end_date})"

    @property
    def label(self) -> str:
        return self.unit.label

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
        """Ended leases are history: kept, readable, and not rewritten."""
        return self.status != LeaseStatus.ENDED

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
                            "A fixed lease has no step up. Choose Step up or Triple net to "
                            "record one."
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
        return self.template in STEPPING_TEMPLATES

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
        if self.lease_id is not None and self.lease.template not in STEPPING_TEMPLATES:
            raise ValidationError(
                {
                    "lease": (
                        "A fixed lease has one rent for its term. Make the lease a step up or "
                        "triple net to record dated amounts."
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
        if self.lease_id is not None and self.lease.template != LeaseTemplate.NNN:
            raise ValidationError({"lease": "Only a triple-net lease carries an NNN amount."})


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
