"""Property responsibilities: the bills a property carries, and each unit's share.

E2. RHP is billed per property for things like water and pruning; each unit carries
its share, divided according to the lease. The office stages a cycle's bill and the
per-unit monthly amounts it produces, and **those stored amounts are what the ledger
charges** — money is never re-derived from a percentage at charge time (ADR-014).

Two rules hold the model together:

* a cycle covers the first ``months`` rent due dates of a lease on or after its
  ``starts_on``, so "which months does this bill pay for?" has one answer;
* once a month has been charged, the cycle and its shares are history: a mistake is
  corrected with an adjustment on the ledger, never by changing what the bill said.
"""

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.dates import due_date_in, due_date_on_or_after, month_after

ZERO = Decimal("0.00")

#: The shortest and longest cycle a responsibility may be staged over, in months.
MINIMUM_CYCLE_MONTHS = 1
MAXIMUM_CYCLE_MONTHS = 12


class ResponsibilityCategory(models.TextChoices):
    """What kind of cost this is, so a tenant's month can be grouped (E2)."""

    UTILITY = "UTILITY", "Utility"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    OTHER = "OTHER", "Other"


class PropertyResponsibility(models.Model):
    """One recurring cost a property carries: water, trash, pruning.

    The bill arrives at the property; the units carry their shares. A
    responsibility is stopped by deactivating it — deleting one would take its
    cycles and the story of what was charged with it.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="responsibilities",
    )
    label = models.CharField(
        max_length=100,
        help_text="What the tenant reads: Water, Trash, Parking, Pruning.",
    )
    category = models.CharField(
        max_length=16,
        choices=ResponsibilityCategory.choices,
        default=ResponsibilityCategory.UTILITY,
        help_text="Groups the charge on the tenant's statement.",
    )
    cycle_months = models.PositiveSmallIntegerField(
        default=3,
        validators=[
            MinValueValidator(MINIMUM_CYCLE_MONTHS),
            MaxValueValidator(MAXIMUM_CYCLE_MONTHS),
        ],
        help_text="How many months one bill covers. A quarterly water bill is 3.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="An inactive responsibility raises no new charges; its history stays.",
    )
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsibilities_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("property__name", "label")
        verbose_name_plural = "property responsibilities"
        constraints = [
            models.UniqueConstraint(
                fields=["property", "label"], name="one_responsibility_per_label"
            )
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.property.name})"

    def clean(self):
        super().clean()
        if self.cycle_months is not None and not (
            MINIMUM_CYCLE_MONTHS <= self.cycle_months <= MAXIMUM_CYCLE_MONTHS
        ):
            raise ValidationError({"cycle_months": "A cycle is between 1 and 12 months long."})

    # Plain methods, not properties: the `property` field above shadows the
    # builtin decorator inside this class body, and a staged cycle must be visible
    # immediately rather than remembered per instance.
    def cycles_ordered(self) -> list[ResponsibilityCycle]:
        return sorted(self.cycles.all(), key=lambda cycle: cycle.starts_on)

    def current_cycle(self) -> ResponsibilityCycle | None:
        """The cycle whose months include today, if one does."""
        today = timezone.localdate()
        applicable = [cycle for cycle in self.cycles_ordered() if cycle.starts_on <= today]
        return applicable[-1] if applicable else None

    def next_cycle(self) -> ResponsibilityCycle | None:
        """The staged cycle starting after today, if there is one."""
        today = timezone.localdate()
        upcoming = [cycle for cycle in self.cycles_ordered() if cycle.starts_on > today]
        return upcoming[0] if upcoming else None

    def cycle_covering(self, day: dt.date) -> ResponsibilityCycle | None:
        """The staged cycle whose months cover ``day``, if any."""
        covered = [cycle for cycle in self.cycles_ordered() if cycle.starts_on <= day]
        return covered[-1] if covered else None


class ResponsibilityCycle(models.Model):
    """One bill for a property responsibility, staged before its months arrive.

    The office stages the bill in advance (the next cycle) while the one in force
    keeps applying, exactly as a triple-net lease's NNN does (E1).
    """

    responsibility = models.ForeignKey(
        PropertyResponsibility,
        on_delete=models.PROTECT,
        related_name="cycles",
    )
    starts_on = models.DateField(help_text="The first month this bill covers.")
    months = models.PositiveSmallIntegerField(
        default=3,
        validators=[
            MinValueValidator(MINIMUM_CYCLE_MONTHS),
            MaxValueValidator(MAXIMUM_CYCLE_MONTHS),
        ],
        help_text="How many monthly charges this bill pays for.",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="What the property was billed for this cycle, in dollars.",
    )
    note = models.CharField(max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsibility_cycles_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["responsibility", "starts_on"], name="one_cycle_per_start_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.responsibility.label} from {self.starts_on} ({self.total_amount})"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.months is not None and not (
            MINIMUM_CYCLE_MONTHS <= self.months <= MAXIMUM_CYCLE_MONTHS
        ):
            raise ValidationError({"months": "A cycle is between 1 and 12 months long."})

    @property
    def monthly_total(self) -> Decimal:
        """The bill divided across the months it covers, to the cent."""
        if not self.months:
            return ZERO
        return (self.total_amount / self.months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def ends_on(self) -> dt.date:
        """The last day of the last month this cycle covers: for display."""
        year, month = month_after(self.starts_on, self.months - 1)
        return dt.date(year, month, calendar.monthrange(year, month)[1])

    def covered_dates(self, lease) -> list[dt.date]:
        """The rent due dates of ``lease`` that this cycle's months pay for.

        The first due date on or after ``starts_on``, then the next ``months − 1``
        monthly due dates, stopping at the end of the tenancy.
        """
        dates: list[dt.date] = []
        due = due_date_on_or_after(self.starts_on, lease.rent_due_day)
        for _ in range(self.months or 0):
            if due > lease.end_date:
                break
            dates.append(due)
            year, month = month_after(due, 1)
            due = due_date_in(year, month, lease.rent_due_day)
        return dates

    def covers(self, day: dt.date, lease) -> bool:
        return day in self.covered_dates(lease)

    @property
    def share_total(self) -> Decimal:
        """What the units' monthly amounts add up to, against the bill's monthly."""
        return sum((share.monthly_amount for share in self.shares.all()), ZERO)


class ResponsibilityShare(models.Model):
    """One unit's monthly share of one cycle's bill.

    Stored per cycle, because the division is not always a formula: RHP has a real
    water bill where one unit is billed for its usage and the other carries the
    remainder. The office sets each figure; RHP proposes them from square footage
    when the responsibility is staged (ADR-014).
    """

    cycle = models.ForeignKey(
        ResponsibilityCycle,
        on_delete=models.PROTECT,
        related_name="shares",
    )
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.PROTECT,
        related_name="responsibility_shares",
    )
    monthly_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Charged every month of the cycle. Zero takes the unit out of it.",
    )
    note = models.CharField(max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsibility_shares_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("cycle__starts_on", "unit__identifier")
        constraints = [
            models.UniqueConstraint(fields=["cycle", "unit"], name="one_share_per_unit_per_cycle")
        ]

    def __str__(self) -> str:
        return f"{self.unit.identifier}: {self.monthly_amount}"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cycle_id and self.unit_id:
            if self.unit.property_id != self.cycle.responsibility.property_id:
                raise ValidationError(
                    {"unit": "That unit is not in the property this responsibility belongs to."}
                )
