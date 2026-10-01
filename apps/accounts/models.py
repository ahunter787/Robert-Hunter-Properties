"""Identity model for RHP.

Phase 0 ships a deliberately *empty* custom user. Django cannot change
``AUTH_USER_MODEL`` after the first migration, and Phase 1 builds roles,
tenant profiles, and staff permissions on top of this model, so the swap has to
happen now — while the database holds no real data. See
``docs/decisions/ADR-002-custom-user.md``.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """An RHP account.

    Phase 1 adds the role model (SUPERADMIN / ADMIN / MANAGER / MAINTENANCE /
    TENANT) and the tenant profile. Nothing is added here yet on purpose: the
    only thing Phase 0 needs from this class is its existence.
    """

    def __str__(self) -> str:
        return self.get_full_name() or self.username
