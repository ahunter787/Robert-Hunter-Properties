"""Admin registration for RHP identity models.

The Django admin is the back office: ``is_staff``/``is_superuser`` gate it, while
the RHP portal is gated by ``role`` (ADR-003).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import LoginAttempt, TenantProfile, User


class TenantProfileInline(admin.StackedInline):
    model = TenantProfile
    extra = 0
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "display_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    inlines = [TenantProfileInline]
    fieldsets = (*DjangoUserAdmin.fieldsets, ("RHP", {"fields": ("role",)}))


@admin.register(TenantProfile)
class TenantProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "preferred_contact_method", "updated_at")
    search_fields = ("user__username", "user__email", "phone")
    autocomplete_fields = ("user",)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "ip", "successful")
    list_filter = ("successful",)
    search_fields = ("username", "ip")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
