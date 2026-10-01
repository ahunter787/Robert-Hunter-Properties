"""Django admin for leases (the back office beside the RHP screens)."""

from django.contrib import admin

from apps.leases.models import Lease, LeaseTenant


class LeaseTenantInline(admin.TabularInline):
    model = LeaseTenant
    extra = 0
    autocomplete_fields = ("tenant",)


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("unit", "start_date", "end_date", "monthly_rent", "status")
    list_filter = ("status", "start_date", "end_date")
    search_fields = ("unit__identifier", "unit__property__name", "lease_tenants__tenant__username")
    autocomplete_fields = ("unit",)
    inlines = [LeaseTenantInline]
    date_hierarchy = "start_date"


@admin.register(LeaseTenant)
class LeaseTenantAdmin(admin.ModelAdmin):
    list_display = ("tenant", "lease", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("tenant__username", "tenant__first_name", "tenant__last_name")
    autocomplete_fields = ("tenant", "lease")
