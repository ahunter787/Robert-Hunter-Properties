"""Server-side authorization for the RHP portal.

Two distinct outcomes, chosen deliberately (ADR-003):

* **Whole-area access** by the wrong role is a ``403`` - the user is
  authenticated, they simply may not be here.
* **An individual record** outside a tenant's own tenancy is a ``404`` - so ids
  cannot be probed to learn what exists.

Nothing in this module may be replaced by hiding navigation: every view that
returns RHP data mixes in one of these classes or calls ``role_required``.
"""

from collections.abc import Callable
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from apps.accounts.models import ADMIN_ROLES, MANAGER_ROLES, STAFF_ROLES, Role

DENIED_MESSAGE = "Your account does not have access to that area."


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only the listed roles; anonymous users are sent to the login page.

    ``allowed_roles`` is filled in by the concrete mixins below.
    """

    allowed_roles: frozenset[str] = frozenset()

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        return user.is_superuser or user.role in self.allowed_roles

    def handle_no_permission(self):
        # Authenticated but wrong role → 403; anonymous → login redirect.
        if self.request.user.is_authenticated:
            raise PermissionDenied(DENIED_MESSAGE)
        return super().handle_no_permission()


class StaffRequiredMixin(RoleRequiredMixin):
    """Any RHP staff role may enter the management area."""

    allowed_roles = STAFF_ROLES


class ManagerRequiredMixin(RoleRequiredMixin):
    """Portfolio work: MANAGER, ADMIN, and SUPERADMIN (the spec's manager scope)."""

    allowed_roles = MANAGER_ROLES


class AdminRequiredMixin(RoleRequiredMixin):
    """Account administration and destructive operations: ADMIN and above."""

    allowed_roles = ADMIN_ROLES


class TenantRequiredMixin(RoleRequiredMixin):
    """The tenant area: tenants only. Staff use the management screens instead."""

    allowed_roles = frozenset({Role.TENANT})


class TenantAreaMixin(TenantRequiredMixin):
    """A tenant's own page, which a staff account reads from the management area.

    A superuser passes every role test by design, so a staff account that landed on
    ``/lease/`` used to be shown the *tenant* empty state — "No lease yet" — which
    reads as a broken account rather than the wrong door (the owner hit exactly this
    while signed in as ``rhpadmin``). Staff are sent to the management home instead,
    the way ``/account/`` already sends them, with a line saying why. Nothing is
    disclosed either way: a staff account has no tenancy of its own to show.
    """

    staff_redirect = "manage:home"

    def test_func(self) -> bool:
        user = self.request.user
        if user.is_authenticated and user.is_rhp_staff:
            return False
        return super().test_func()

    def handle_no_permission(self):
        user = self.request.user
        if user.is_authenticated and user.is_rhp_staff:
            messages.info(
                self.request,
                "That page is a tenant's own view. Your account works from the management "
                "area, where the same information sits on the lease.",
            )
            return redirect(self.staff_redirect)
        return super().handle_no_permission()


class SuperadminRequiredMixin(RoleRequiredMixin):
    """Role changes and other privileged operations."""

    allowed_roles = frozenset({Role.SUPERADMIN})


def role_required(*roles: str) -> Callable:
    """Function-view equivalent of ``RoleRequiredMixin``."""

    allowed = frozenset(roles)

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in allowed:
                return view(request, *args, **kwargs)
            raise PermissionDenied(DENIED_MESSAGE)

        return wrapper

    return decorator


def tenant_scope(user, queryset, owner_field: str = "user"):
    """Restrict a queryset to what ``user`` may read.

    Staff see everything; a tenant sees only rows they own. Phase 2+ reuses this
    pattern for leases, charges, documents, and maintenance requests, where
    ``owner_field`` becomes a relation such as ``lease__tenants``.
    """
    if user.is_authenticated and user.is_rhp_staff:
        return queryset
    return queryset.filter(**{owner_field: user})
