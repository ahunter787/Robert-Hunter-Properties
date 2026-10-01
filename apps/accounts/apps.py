"""App configuration for RHP accounts."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    # Explicit label keeps table names and AUTH_USER_MODEL references stable
    # (`accounts.User` / `accounts_user`) regardless of the package path.
    label = "accounts"
    verbose_name = "Accounts"
