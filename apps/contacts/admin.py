"""Django admin for people (the back office beside the RHP screens)."""

from django.contrib import admin

from apps.contacts.models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email", "phone", "portal_user")
    search_fields = ("first_name", "last_name", "email", "portal_user__username")
