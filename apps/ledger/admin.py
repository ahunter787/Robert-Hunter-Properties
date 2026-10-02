"""Django admin for the ledger: read-only, by design.

The RHP screens are the interface for money, and they enforce the rules an admin
form cannot: no editing, no deleting, corrections as new entries. The back office
can look at a ledger and cannot rewrite one.
"""

from django.contrib import admin

from apps.ledger.models import Charge, Payment


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("due_date", "lease", "kind", "direction", "amount", "description")
    list_filter = ("kind", "direction", "due_date")
    search_fields = ("description", "lease__unit__identifier", "lease__unit__property__name")
    date_hierarchy = "due_date"
    readonly_fields = tuple(field.name for field in Charge._meta.fields)
    autocomplete_fields = ("lease",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_date", "lease", "kind", "amount", "method", "status")
    list_filter = ("kind", "status", "method", "payment_date")
    search_fields = ("external_reference", "lease__unit__identifier")
    date_hierarchy = "payment_date"
    readonly_fields = tuple(field.name for field in Payment._meta.fields)
    autocomplete_fields = ("lease",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
