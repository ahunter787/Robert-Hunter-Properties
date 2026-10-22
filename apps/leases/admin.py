"""Django admin for leases (the back office beside the RHP screens)."""

from django.contrib import admin

from apps.leases.models import Lease, LeaseTenant


class LeaseTenantInline(admin.TabularInline):
    model = LeaseTenant
    extra = 0
    autocomplete_fields = ("person",)


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("unit", "start_date", "end_date", "monthly_rent", "status")
    list_filter = ("status", "start_date", "end_date")
    search_fields = (
        "unit__identifier",
        "unit__property__name",
        "lease_tenants__person__last_name",
        "lease_tenants__person__first_name",
    )
    autocomplete_fields = ("unit",)
    inlines = [LeaseTenantInline]
    date_hierarchy = "start_date"


@admin.register(LeaseTenant)
class LeaseTenantAdmin(admin.ModelAdmin):
    list_display = ("person", "role", "lease", "is_primary")
    list_filter = ("role", "is_primary")
    search_fields = (
        "person__first_name",
        "person__last_name",
        "person__email",
        "person__portal_user__username",
    )
    autocomplete_fields = ("person", "lease")
