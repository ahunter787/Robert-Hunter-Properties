"""Forms for the portfolio screens."""

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.common.forms import StyledModelForm
from apps.properties.models import Property, Unit


class PropertyForm(StyledModelForm):
    class Meta:
        model = Property
        fields = ["name", "street", "city", "state", "postal_code", "notes", "is_active"]
        labels = {"is_active": "In service"}
        help_texts = {
            "is_active": "Uncheck to retire the property without losing its history.",
        }

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


class UnitForm(StyledModelForm):
    class Meta:
        model = Unit
        fields = ["property", "identifier", "bedrooms", "bathrooms", "is_active"]
        labels = {"is_active": "In service"}
        help_texts = {"is_active": "Uncheck for a unit that is out of service."}

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
        return cleaned
