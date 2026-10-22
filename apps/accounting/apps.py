from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounting"
    verbose_name = "Accounting"

    def ready(self):
        from apps.accounting import signals  # noqa: F401
