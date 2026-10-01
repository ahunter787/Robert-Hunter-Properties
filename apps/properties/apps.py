"""App configuration for the portfolio."""

from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.properties"
    label = "properties"
    verbose_name = "Portfolio"

    def ready(self):
        # Registers the banner-file cleanup; imported here because models are not
        # loaded yet when the app config is created.
        from apps.properties import signals  # noqa: F401
