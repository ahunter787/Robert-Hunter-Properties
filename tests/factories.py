"""Small builders for RHP tests.

Plain functions rather than a factory library: the shapes are simple, and a new
dependency is not worth its weight here (see AGENTS.md).
"""

from decimal import Decimal

from apps.accounts.models import Role, TenantProfile, User
from apps.properties.models import Property, Unit

DEFAULT_PASSWORD = "unit-test-password-41"


def make_user(
    *,
    username: str = "rhp-user",
    role: str = Role.TENANT,
    password: str | None = DEFAULT_PASSWORD,
    with_profile: bool | None = None,
    **fields,
) -> User:
    """Create a user with ``role``; tenants get a tenant profile by default."""
    user = User.objects.create_user(username=username, password=password, role=role, **fields)
    if with_profile is None:
        with_profile = role == Role.TENANT
    if with_profile:
        TenantProfile.objects.get_or_create(user=user)
    return user


def make_tenant(**kwargs) -> User:
    kwargs.setdefault("username", "tenant")
    return make_user(role=Role.TENANT, **kwargs)


def make_manager(**kwargs) -> User:
    kwargs.setdefault("username", "rhp-manager")
    return make_user(role=Role.MANAGER, **kwargs)


def make_maintenance(**kwargs) -> User:
    kwargs.setdefault("username", "rhp-maintenance")
    return make_user(role=Role.MAINTENANCE, **kwargs)


def make_admin(**kwargs) -> User:
    kwargs.setdefault("username", "rhp-admin")
    return make_user(role=Role.ADMIN, **kwargs)


def make_superadmin(**kwargs) -> User:
    kwargs.setdefault("username", "rhp-superadmin")
    kwargs.setdefault("password", DEFAULT_PASSWORD)
    return User.objects.create_superuser(**kwargs)


def make_invited_tenant(*, username: str = "invited-tenant", email: str = "invited@example.com"):
    """A tenant account that was created but has never set a password."""
    user = User.objects.create_user(username=username, email=email, role=Role.TENANT)
    TenantProfile.objects.create(user=user)
    return user


def invitation_path_from_email(body: str) -> str:
    """Pull the site-relative invitation link out of a rendered email body."""
    import re
    from urllib.parse import urlparse

    match = re.search(r"https?://\S+/account/invite/\S+", body)
    assert match, f"no invitation link in email body:\n{body}"
    return urlparse(match.group(0)).path


def password_reset_path_from_email(body: str) -> str:
    import re
    from urllib.parse import urlparse

    match = re.search(r"https?://\S+/account/password-reset/\S+", body)
    assert match, f"no password-reset link in email body:\n{body}"
    return urlparse(match.group(0)).path


# --- Portfolio ------------------------------------------------------------


def make_property(
    *,
    name: str = "Maple Street Duplex",
    street: str = "12 Maple St",
    city: str = "Springfield",
    state: str = "IL",
    postal_code: str = "62704",
    **fields,
) -> Property:
    return Property.objects.create(
        name=name,
        street=street,
        city=city,
        state=state,
        postal_code=postal_code,
        **fields,
    )


def make_unit(
    for_property: Property | None = None,
    *,
    identifier: str = "1",
    bedrooms: int | None = 2,
    bathrooms: Decimal | None = Decimal("1.0"),
    **fields,
) -> Unit:
    if for_property is None:
        for_property = make_property()
    return Unit.objects.create(
        property=for_property,
        identifier=identifier,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        **fields,
    )
