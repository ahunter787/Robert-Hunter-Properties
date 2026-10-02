"""Django admin for the portfolio (the back office beside the RHP screens)."""

from django.contrib import admin
from django.db.models import Count

from apps.properties.models import Amenity, Property, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0
    fields = ("identifier", "square_feet", "bedrooms", "bathrooms", "is_active")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "property_type", "city", "state", "is_active", "unit_total")
    list_filter = ("property_type", "is_active", "state")
    search_fields = ("name", "street", "city", "postal_code")
    inlines = [UnitInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_units=Count("units"))

    @admin.display(ordering="_units", description="Units")
    def unit_total(self, obj):
        return obj._units


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("identifier", "property", "square_feet", "bedrooms", "bathrooms", "is_active")
    list_filter = ("is_active",)
    search_fields = ("identifier", "property__name")
    autocomplete_fields = ("property", "amenities")
    filter_horizontal = ("amenities",)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    """Add or rename amenities here; they feed the unit form's picker.

    Retire an amenity (untick *is active*) rather than deleting it: deleting one
    removes it from every unit that had it.
    """

    list_display = ("name", "is_active", "units_using")
    list_filter = ("is_active",)
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_units=Count("units"))

    @admin.display(ordering="_units", description="Units")
    def units_using(self, obj):
        return obj._units
