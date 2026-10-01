"""Portfolio models: the properties RHP manages and their units.

Phase 2 models the portfolio itself. Occupancy, vacancy, and rent are properties
of a *lease*, so they arrive with Phase 3 - the screens say so explicitly rather
than showing a zero that looks like real data.
"""

from pathlib import Path
from uuid import uuid4

from django.db import models
from django.db.models.functions import Lower
from django.utils.functional import cached_property

from apps.properties.constants import (  # noqa: F401 - USState re-exported
    ZIP_CODE_VALIDATOR,
    UnitType,
    USState,
)


def property_banner_path(instance, filename: str) -> str:
    """Randomised storage path for a banner.

    Never the client's filename: uploads are stored under a generated name so a
    crafted name cannot influence where a file lands (docs/security.md).
    """
    suffix = Path(filename).suffix.lower()
    if len(suffix) > 10 or not suffix.isascii():
        suffix = ""
    return f"property_banners/{uuid4().hex}{suffix}"


class PropertyQuerySet(models.QuerySet):
    """Query helpers the later phases reuse (leases, documents, maintenance)."""

    def active(self):
        return self.filter(is_active=True)


class Property(models.Model):
    """A building RHP manages, with one or more units."""

    name = models.CharField(
        max_length=120,
        help_text="How staff refer to it, for example 'Maple Street Duplex'.",
    )
    street = models.CharField("street address", max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, choices=USState.choices)
    postal_code = models.CharField("ZIP code", max_length=10, validators=[ZIP_CODE_VALIDATOR])
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive properties stay in history but drop out of pickers.",
    )
    notes = models.TextField(blank=True)
    # Stored measurement, not a float: six decimals is about 11 cm.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    banner_image = models.ImageField(upload_to=property_banner_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PropertyQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "properties"
        ordering = ("name",)
        constraints = [
            # Case-insensitive: "Maple St" and "maple st" are the same building
            # as far as staff are concerned, and a duplicate would split records.
            models.UniqueConstraint(Lower("name"), name="property_name_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def address_line(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.postal_code}"

    @property
    def has_map_pin(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_banner(self) -> bool:
        return bool(self.banner_image)


class UnitQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Unit(models.Model):
    """A rentable unit inside a property."""

    property = models.ForeignKey(
        Property,
        # PROTECT, not CASCADE: deleting a property must never silently take its
        # units (and later its lease history) with it. Deactivate instead.
        on_delete=models.PROTECT,
        related_name="units",
    )
    identifier = models.CharField(
        max_length=32,
        help_text="Label used inside the property, for example '1', 'A', or 'Rear'.",
    )
    unit_type = models.CharField(
        max_length=12,
        choices=UnitType.choices,
        default=UnitType.RESIDENTIAL,
        db_index=True,
        help_text="Commercial units have no bedrooms or bathrooms.",
    )
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Half baths are allowed, for example 1.5.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Out-of-service units stay in history but drop out of pickers.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UnitQuerySet.as_manager()

    class Meta:
        ordering = ("property__name", "identifier")
        constraints = [
            models.UniqueConstraint(
                fields=["property", "identifier"],
                name="unit_identifier_per_property",
            ),
        ]

    def __str__(self) -> str:
        return self.label

    # cached_property, not @property: the `property` field above shadows the
    # builtin decorator inside this class body.
    @cached_property
    def display_name(self) -> str:
        """The unit's own name. The property is shown separately, see ``label``."""
        return self.identifier

    @cached_property
    def label(self) -> str:
        """Single-line label: the unit first, then its property."""
        return f"{self.identifier} - {self.property.name}"

    @cached_property
    def is_commercial(self) -> bool:
        return self.unit_type == UnitType.COMMERCIAL

    # --- Occupancy --------------------------------------------------------
    # The definition lives in apps.leases (LeaseQuerySet.current): a unit is
    # occupied while an active lease's term covers today. These helpers read that
    # through the reverse relation, so there is one definition and no import
    # cycle between the two apps.

    @cached_property
    def current_lease(self):
        """The lease occupying this unit today, if any."""
        return self.leases.current().first()

    @cached_property
    def occupants(self):
        """The people on the current lease. Prefetch ``lease_tenants__tenant``."""
        lease = self.current_lease
        if lease is None:
            return []
        return [link.tenant for link in lease.lease_tenants.select_related("tenant")]

    @cached_property
    def is_vacant(self) -> bool:
        """In service, with nobody currently on a lease."""
        return self.is_active and self.current_lease is None

    @cached_property
    def is_occupied(self) -> bool:
        """In service, with a current tenancy.

        A unit that is out of service is a third state: its tenancy stays in the
        records (see ``current_lease``), but it counts as neither occupied nor
        vacant, because it cannot be let.
        """
        return self.is_active and self.current_lease is not None
