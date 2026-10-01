"""App configuration for leases."""

from django.apps import AppConfig


class LeasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leases"
    label = "leases"
    verbose_name = "Leasing"

    def ready(self):
        # Registers the lease-document cleanup; imported here because models are
        # not loaded yet when the app config is created.
        from apps.leases import signals  # noqa: F401
