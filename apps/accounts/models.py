"""Identity models for RHP.

Phase 0 fixed ``AUTH_USER_MODEL`` with an empty user (ADR-002). Phase 1 adds the
role that gates the portal, the tenant profile that carries contact details, and
the login-attempt ledger the throttle reads.

Django's ``is_staff``/``is_superuser`` keep gating ``/admin/``; ``role`` gates the
RHP portal. They are related but deliberately separate concepts - see
``docs/decisions/ADR-003-role-on-user-model.md``.
"""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    """The five roles in the master specification."""

    SUPERADMIN = "SUPERADMIN", "Superadmin"
    ADMIN = "ADMIN", "Admin"
    MANAGER = "MANAGER", "Manager"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    TENANT = "TENANT", "Tenant"


#: Roles that may reach the management portal at all.
STAFF_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.MAINTENANCE})
#: Roles that may administer accounts.
ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN})


class UserManager(DjangoUserManager):
    """Keeps ``createsuperuser`` consistent with the role model."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.SUPERADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """An RHP account.

    ``role`` decides which portal area the account may reach. The default is
    TENANT because staff create tenant accounts; staff accounts get their role
    from the admin or from a superadmin.
    """

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TENANT,
        db_index=True,
        help_text="Determines which parts of RHP this account may use.",
    )

    objects = UserManager()

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def is_rhp_staff(self) -> bool:
        """True for any RHP staff role (a superuser always qualifies)."""
        return self.is_superuser or self.role in STAFF_ROLES

    @property
    def is_admin_or_above(self) -> bool:
        return self.is_superuser or self.role in ADMIN_ROLES

    @property
    def is_superadmin(self) -> bool:
        return self.is_superuser or self.role == Role.SUPERADMIN

    @property
    def is_tenant(self) -> bool:
        return not self.is_rhp_staff

    def __str__(self) -> str:
        return self.display_name


class PreferredContact(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone call"
    TEXT = "text", "Text message"


class TenantProfile(models.Model):
    """Contact details for a tenant.

    ``notes`` is staff-only: excluded from every tenant-facing form and never
    rendered to a tenant - the first instance of the specification's "internal
    notes are never exposed" rule.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tenant_profile")
    phone = models.CharField("phone number", max_length=32, blank=True)
    preferred_contact_method = models.CharField(
        max_length=10,
        choices=PreferredContact.choices,
        default=PreferredContact.EMAIL,
    )
    notes = models.TextField(
        blank=True,
        help_text="Internal RHP notes about this tenant. Never shown to the tenant.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "tenant profile"
        verbose_name_plural = "tenant profiles"

    def __str__(self) -> str:
        return f"{self.user.display_name} (tenant profile)"


class LoginAttempt(models.Model):
    """One row per login attempt; the throttle counts failures in a window.

    A database ledger (rather than the cache) is used because RHP intentionally
    runs without Redis and gunicorn spawns several workers, so an in-process
    cache would throttle each worker separately.
    """

    username = models.CharField(max_length=150, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["username", "created_at"], name="loginattempt_user_time"),
            models.Index(fields=["ip", "created_at"], name="loginattempt_ip_time"),
        ]

    def __str__(self) -> str:
        outcome = "success" if self.successful else "failure"
        return f"{self.username} @ {self.ip or 'unknown'} ({outcome})"
