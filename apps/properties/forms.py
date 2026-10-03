"""Forms for the portfolio screens."""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.common.forms import StyledModelForm
from apps.common.images import validate_image_upload
from apps.properties.constants import PropertyType
from apps.properties.locations import parse_coordinates
from apps.properties.models import Amenity, Property, Unit


class PropertyForm(StyledModelForm):
    """Property details, its map pin, and its banner photo."""

    coordinates = forms.CharField(
        required=False,
        label="Google Maps link or coordinates",
        help_text=(
            "Paste a Google Maps link that contains the pin, or a pair such as "
            "45.5231, -122.6765. Leave blank to remove the pin."
        ),
    )
    remove_banner = forms.BooleanField(
        required=False,
        label="Remove the current banner photo",
        help_text="Uploading a new photo replaces the current one.",
    )

    class Meta:
        model = Property
        fields = [
            "name",
            "property_type",
            "street",
            "city",
            "state",
            "postal_code",
            "cam_rate_per_sqft",
            "notes",
            "banner_image",
            "is_active",
        ]
        labels = {"is_active": "In service", "banner_image": "Banner photo"}
        help_texts = {
            "is_active": "Uncheck to retire the property without losing its history.",
            "banner_image": "JPEG, PNG, or WebP. Shown as the header image on the property page.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.has_map_pin:
            self.fields[
                "coordinates"
            ].initial = f"{self.instance.latitude}, {self.instance.longitude}"
        if not self.instance.pk:
            # Nothing to remove before the first save.
            self.fields.pop("remove_banner")

    def clean_name(self) -> str:
        name = " ".join(self.cleaned_data["name"].split())
        # Same rule as the database constraint, with a message a person can read.
        clash = Property.objects.filter(name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("A property with that name already exists.")
        return name

    def clean_city(self) -> str:
        return " ".join(self.cleaned_data["city"].split())

    def clean_banner_image(self):
        return validate_image_upload(
            self.cleaned_data.get("banner_image"),
            max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024,
        )

    def clean_property_type(self) -> str:
        """Refuse to strand residential detail under a commercial designation.

        Turning a property commercial while its units still record bedrooms or
        bathrooms would leave data the screens then call "not applicable" — so it
        is refused, with the units named, rather than silently cleared.
        """
        property_type = self.cleaned_data["property_type"]
        if (
            self.instance.pk
            and property_type == PropertyType.COMMERCIAL
            and not self.instance.is_commercial
        ):
            furnished = self.instance.units.filter(
                Q(bedrooms__isnull=False) | Q(bathrooms__isnull=False)
            )
            if furnished.exists():
                names = ", ".join(unit.identifier for unit in furnished[:5])
                more = "" if furnished.count() <= 5 else f" and {furnished.count() - 5} more"
                raise ValidationError(
                    f"{self.instance.name} has units with bedrooms or bathrooms recorded "
                    f"({names}{more}). Clear those first, then set the property to commercial."
                )
        return property_type

    def clean(self):
        cleaned = super().clean()

        try:
            cleaned["coordinates"] = parse_coordinates(cleaned.get("coordinates", ""))
        except ValidationError as error:
            self.add_error("coordinates", error)

        # Only a *fresh* upload conflicts with removal: on an edit form the field
        # still holds the file already on disk, which is truthy.
        if cleaned.get("remove_banner") and self.files.get("banner_image"):
            self.add_error(
                "remove_banner", "Keep the new photo, or tick this to remove the current one."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.latitude, instance.longitude = self.cleaned_data.get("coordinates") or (None, None)
        if self.cleaned_data.get("remove_banner"):
            instance.banner_image = None
        if commit:
            instance.save()
        return instance


class UnitForm(StyledModelForm):
    class Meta:
        model = Unit
        fields = [
            "property",
            "identifier",
            "square_feet",
            "bedrooms",
            "bathrooms",
            "amenities",
            "is_active",
        ]
        labels = {"is_active": "In service"}
        help_texts = {
            "is_active": "Uncheck for a unit that is out of service.",
            "bedrooms": "Residential properties only.",
            "bathrooms": "Residential properties only. Half baths are allowed, for example 1.5.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only in-service properties can take new units - but a unit already on a
        # retired property keeps that property selectable, otherwise saving the
        # form would silently move it somewhere else.
        properties = Property.objects.filter(is_active=True)
        if self.instance.pk:
            properties = Property.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.property_id)
            )
        self.fields["property"].queryset = properties.order_by("name")
        self.fields["property"].empty_label = "Select a property"

        # Retired amenities stay on the units that have them, but are no longer
        # offered; a unit being edited keeps any it already has selectable.
        offered = Amenity.objects.filter(is_active=True)
        if self.instance.pk:
            offered = Amenity.objects.filter(
                Q(is_active=True) | Q(pk__in=self.instance.amenities.values("pk"))
            )
        self.fields["amenities"].queryset = offered.order_by("name")
        self.fields["amenities"].label = "Amenities"

    def clean_identifier(self) -> str:
        identifier = " ".join(self.cleaned_data["identifier"].split())
        if not identifier:
            raise ValidationError("Enter a unit identifier.")
        return identifier

    def clean(self):
        cleaned = super().clean()

        property_ = cleaned.get("property")
        identifier = cleaned.get("identifier")
        if property_ and identifier:
            clash = Unit.objects.filter(property=property_, identifier=identifier)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("identifier", "That identifier is already used at this property.")

        # Bedrooms and bathrooms describe residential space, so they are not
        # meaningful in a commercial property. Enforced here rather than by hiding
        # the inputs, so the rule holds whatever the browser sends — and checked
        # against the *submitted* property, so moving a unit into a commercial
        # building is refused rather than quietly saved.
        if (
            property_
            and property_.is_commercial
            and (cleaned.get("bedrooms") is not None or cleaned.get("bathrooms") is not None)
        ):
            self.add_error(
                None,
                f"{property_.name} is a commercial property, so bedrooms and bathrooms are "
                "not recorded for its units. Leave them blank.",
            )
        return cleaned
