"""App configuration for property responsibilities."""

from django.apps import AppConfig


class ResponsibilitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.responsibilities"
    label = "responsibilities"
    verbose_name = "Property responsibilities"
