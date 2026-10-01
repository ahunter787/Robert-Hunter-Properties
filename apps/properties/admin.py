"""Django admin for the portfolio (the back office beside the RHP screens)."""

from django.contrib import admin
from django.db.models import Count

from apps.properties.models import Property, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0
    fields = ("identifier", "bedrooms", "bathrooms", "is_active")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "is_active", "unit_total")
    list_filter = ("is_active", "state")
    search_fields = ("name", "street", "city", "postal_code")
    inlines = [UnitInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_units=Count("units"))

    @admin.display(ordering="_units", description="Units")
    def unit_total(self, obj):
        return obj._units


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("identifier", "property", "bedrooms", "bathrooms", "is_active")
    list_filter = ("is_active",)
    search_fields = ("identifier", "property__name")
    autocomplete_fields = ("property",)
