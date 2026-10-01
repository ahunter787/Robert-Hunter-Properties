"""Forms for the portfolio screens."""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from PIL import Image

from apps.common.forms import StyledModelForm
from apps.properties.constants import (
    BANNER_ALLOWED_CONTENT_TYPES,
    BANNER_MAX_DIMENSION,
    UnitType,
)
from apps.properties.locations import parse_coordinates
from apps.properties.models import Property, Unit


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
            "street",
            "city",
            "state",
            "postal_code",
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
        image = self.cleaned_data.get("banner_image")
        # No content_type means the field is holding the file already on disk
        # rather than a fresh upload. Django has validated that one, and opening
        # a stored file here would leave a handle for the test suite to trip over.
        if not image or not hasattr(image, "content_type"):
            return image

        max_bytes = settings.RHP_MAX_UPLOAD_MB * 1024 * 1024
        if image.size > max_bytes:
            raise ValidationError(
                f"That image is larger than {settings.RHP_MAX_UPLOAD_MB} MB. "
                "Resize it and try again."
            )

        content_type = getattr(image, "content_type", "")
        if content_type and content_type not in BANNER_ALLOWED_CONTENT_TYPES:
            raise ValidationError("Upload a JPEG, PNG, or WebP image.")

        try:
            with Image.open(image) as opened:
                width, height = opened.size
        except Exception as error:  # noqa: BLE001 - Pillow raises several types
            raise ValidationError("That file is not an image RHP can read.") from error
        finally:
            # Pillow leaves the pointer inside the file; the storage backend needs
            # to read it from the start.
            image.seek(0)

        if width > BANNER_MAX_DIMENSION or height > BANNER_MAX_DIMENSION:
            raise ValidationError(
                f"That image is larger than {BANNER_MAX_DIMENSION}×{BANNER_MAX_DIMENSION} pixels."
            )
        return image

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
            "unit_type",
            "bedrooms",
            "bathrooms",
            "is_active",
        ]
        labels = {"is_active": "In service", "unit_type": "Unit type"}
        help_texts = {
            "is_active": "Uncheck for a unit that is out of service.",
            "bedrooms": "Residential units only.",
            "bathrooms": "Residential units only. Half baths are allowed, for example 1.5.",
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
        # meaningful on a commercial unit. Enforced here rather than by hiding the
        # inputs, so the rule holds whatever the browser sends.
        if cleaned.get("unit_type") == UnitType.COMMERCIAL and (
            cleaned.get("bedrooms") is not None or cleaned.get("bathrooms") is not None
        ):
            self.add_error(
                None,
                "Bedrooms and bathrooms describe residential units; leave them blank for a "
                "commercial unit.",
            )
        return cleaned
