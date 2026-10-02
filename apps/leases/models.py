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
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.dates import ordinal
from apps.properties.models import Unit


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
        help_text="Rent per month, in dollars.",
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

    def rent_for(self, on_date):
        """What this lease charges per month on a given date.

        One amount for the whole term today. A lease whose rent steps up over its
        term would answer this per period, which is why callers ask the lease
        rather than reading the field directly (the rent-schedule extension, not
        yet built).
        """
        return self.monthly_rent

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
