"""Portfolio models: the properties RHP manages and their units.

Phase 2 models the portfolio itself. Occupancy, vacancy, and rent are properties
of a *lease*, so they arrive with Phase 3 - the screens say so explicitly rather
than showing a zero that looks like real data.
"""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.functional import cached_property

from apps.properties.constants import (  # noqa: F401 - USState re-exported
    ZIP_CODE_VALIDATOR,
    PropertyType,
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
    # The designation belongs to the building, not to each unit: a property is
    # residential or commercial, and its units inherit that (ADR-006 revision).
    property_type = models.CharField(
        max_length=16,
        choices=PropertyType.choices,
        default=PropertyType.RESIDENTIAL,
        db_index=True,
        help_text="Bedrooms and bathrooms are only recorded for units in a residential property.",
    )
    notes = models.TextField(blank=True)
    # The CAM rate the lease quotes: a charge per square foot, folded into base
    # rent rather than charged to the tenant (E2).
    cam_rate_per_sqft = models.DecimalField(
        "CAM rate per square foot",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Optional. Common area maintenance per square foot, for reference.",
    )
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

    @property
    def is_commercial(self) -> bool:
        return self.property_type == PropertyType.COMMERCIAL

    @property
    def is_residential(self) -> bool:
        return self.property_type == PropertyType.RESIDENTIAL

    # --- Size, for dividing a property's bills between its units (E2) --------

    @property
    def total_square_feet(self) -> int | None:
        """Every recorded unit size added up; ``None`` when no unit records one.

        Derived rather than stored, so a property's size cannot disagree with the
        units inside it.
        """
        total = sum(unit.square_feet or 0 for unit in self.units.all())
        return total or None

    @property
    def cam_rate(self) -> Decimal | None:
        return self.cam_rate_per_sqft


class Amenity(models.Model):
    """Something a unit offers, chosen from a list staff maintain.

    A row rather than a fixed choice list so an amenity can be added or renamed
    without a code change. Amenities in use are **retired** (``is_active``),
    never deleted: deleting one would quietly change every unit that had it.
    """

    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Retired amenities stay on the units that have them but leave the picker.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "amenities"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


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
    square_feet = models.PositiveIntegerField(
        "square feet",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(1_000_000)],
        help_text="Optional. Leave blank when the size is not known.",
    )
    amenities = models.ManyToManyField(
        Amenity,
        blank=True,
        related_name="units",
        help_text="Hold Ctrl (or Cmd) to choose more than one.",
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
        """A unit is commercial because its building is (ADR-006 revision)."""
        return self.property.is_commercial

    @cached_property
    def share_of_property(self) -> Decimal | None:
        """This unit's share of the property's size, as a percentage (E2).

        The basis for dividing a property's bills between its units. ``None`` when
        no unit in the property records a size, so a screen says "split evenly"
        rather than pretending to know.
        """
        total = self.property.total_square_feet
        if not total or not self.square_feet:
            return None
        share = (Decimal(self.square_feet) / Decimal(total)) * Decimal("100")
        return share.quantize(Decimal("0.01"))

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
        vacant, because it cannot be rented.
        """
        return self.is_active and self.current_lease is not None
