"""App configuration for documents."""

from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documents"

    def ready(self):
        # Registers the stored-file cleanup; imported here because models are not
        # loaded yet when the app config is created.
        from apps.documents import signals  # noqa: F401
