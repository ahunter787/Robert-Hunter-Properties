"""Django admin for the audit trail: readable, never writable."""

from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "summary", "actor", "object_type", "object_id")
    list_filter = ("action", "created_at")
    search_fields = ("summary", "object_type", "actor__username")
    date_hierarchy = "created_at"
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
