"""Login throttling.

RHP deliberately runs without Redis, and gunicorn spawns several workers, so an
in-process cache would throttle each worker separately. A small database ledger
is accurate across workers, survives restarts, and adds no dependency
(ADR-004). Phase 12 adds proxy-level limiting on top; this is the application
floor.
"""

import datetime as dt
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import LoginAttempt

#: Attempt rows are pruned opportunistically once they are this old.
PRUNE_AFTER = dt.timedelta(hours=24)


def client_ip(request) -> str | None:
    """Best-effort client address.

    ``X-Forwarded-For`` is honoured only when ``RHP_TRUST_PROXY_HEADERS`` is on,
    because an untrusted client can otherwise forge the header to evade the
    throttle - or to pin a lockout on somebody else's address.
    """
    if settings.RHP_TRUST_PROXY_HEADERS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


@dataclass(frozen=True)
class LockState:
    """Whether a login attempt should be refused, and for how much longer."""

    locked: bool
    retry_after: dt.timedelta | None = None

    @property
    def retry_after_minutes(self) -> int:
        if self.retry_after is None:
            return 0
        return max(1, int(self.retry_after.total_seconds() // 60) + 1)


class LoginThrottle:
    """Counts recent failures per account and per address."""

    def __init__(
        self,
        *,
        max_attempts: int | None = None,
        window_minutes: int | None = None,
        lockout_minutes: int | None = None,
    ) -> None:
        self.max_attempts = max_attempts or settings.RHP_LOGIN_MAX_ATTEMPTS
        self.window = dt.timedelta(minutes=window_minutes or settings.RHP_LOGIN_WINDOW_MINUTES)
        self.lockout = dt.timedelta(minutes=lockout_minutes or settings.RHP_LOGIN_LOCKOUT_MINUTES)

    @staticmethod
    def normalize_username(username: str | None) -> str:
        return (username or "").strip().lower()

    def _recent_failures(self, username: str, ip: str | None):
        since = timezone.now() - self.window
        attempts = LoginAttempt.objects.filter(successful=False, created_at__gte=since)
        if ip:
            return attempts.filter(Q(username=username) | Q(ip=ip))
        return attempts.filter(username=username)

    def state(self, username: str | None, ip: str | None) -> LockState:
        """Lock once the failure budget is spent inside the current window."""
        name = self.normalize_username(username)
        failures = list(self._recent_failures(name, ip).values_list("created_at", flat=True))
        if len(failures) < self.max_attempts:
            return LockState(locked=False)

        remaining = (max(failures) + self.lockout) - timezone.now()
        if remaining <= dt.timedelta(0):
            # The lockout has elapsed; the attempt may proceed again.
            return LockState(locked=False)
        return LockState(locked=True, retry_after=remaining)

    def record_failure(self, username: str | None, ip: str | None) -> None:
        LoginAttempt.objects.create(
            username=self.normalize_username(username), ip=ip, successful=False
        )
        self.prune()

    def record_success(self, username: str | None, ip: str | None) -> None:
        """Clear this account's failures and note the successful attempt."""
        name = self.normalize_username(username)
        LoginAttempt.objects.filter(username=name, successful=False).delete()
        LoginAttempt.objects.create(username=name, ip=ip, successful=True)

    def reset(self, username: str | None = None, ip: str | None = None) -> int:
        """Support escape hatch: forget attempts for an account or an address."""
        if not username and not ip:
            return 0
        queryset = LoginAttempt.objects.all()
        if username:
            queryset = queryset.filter(username=self.normalize_username(username))
        if ip:
            queryset = queryset.filter(ip=ip)
        deleted, _ = queryset.delete()
        return deleted

    def prune(self) -> None:
        LoginAttempt.objects.filter(created_at__lt=timezone.now() - PRUNE_AFTER).delete()
