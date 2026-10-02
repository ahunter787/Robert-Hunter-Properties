"""Small builders for RHP tests.

Plain functions rather than a factory library: the shapes are simple, and a new
dependency is not worth its weight here (see AGENTS.md).
"""

import datetime as dt
import itertools
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import Role, TenantProfile, User
from apps.leases.models import Lease, LeaseStatus, LeaseTenant
from apps.ledger.models import (
    Charge,
    ChargeKind,
    Direction,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from apps.properties.constants import PropertyType
from apps.properties.models import Amenity, Property, Unit

DEFAULT_PASSWORD = "unit-test-password-41"

#: Keeps implicit property names distinct across a test.
_PROPERTY_SEQUENCE = itertools.count(1)


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
    property_type: str = PropertyType.RESIDENTIAL,
    street: str = "12 Maple St",
    city: str = "Springfield",
    state: str = "IL",
    postal_code: str = "62704",
    **fields,
) -> Property:
    return Property.objects.create(
        name=name,
        property_type=property_type,
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
    square_feet: int | None = None,
    amenities=(),
    bedrooms: int | None = 2,
    bathrooms: Decimal | None = Decimal("1.0"),
    **fields,
) -> Unit:
    if for_property is None:
        # Property names are unique, so an implicit property needs a distinct one
        # whenever a test builds several units.
        for_property = make_property(name=f"Test Property {next(_PROPERTY_SEQUENCE)}")
    if for_property.is_commercial:
        # A commercial property cannot carry residential details; the form
        # enforces it, and the factory should not build a state the app refuses.
        bedrooms = None
        bathrooms = None
    unit = Unit.objects.create(
        property=for_property,
        identifier=identifier,
        square_feet=square_feet,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        **fields,
    )
    if amenities:
        unit.amenities.set(amenities)
    return unit


def make_amenity(name: str = "Parking", *, is_active: bool = True) -> Amenity:
    """An amenity by name. The default list is seeded by a migration, so this
    adopts an existing row rather than colliding with it."""
    amenity, _ = Amenity.objects.get_or_create(name=name, defaults={"is_active": is_active})
    return amenity


# --- Leasing --------------------------------------------------------------


def make_lease(
    unit: Unit | None = None,
    *,
    tenants=(),
    status: str = LeaseStatus.ACTIVE,
    start_date=None,
    end_date=None,
    monthly_rent: Decimal = Decimal("1850.00"),
    deposit: Decimal = Decimal("1850.00"),
    rent_due_day: int = 1,
    **fields,
) -> Lease:
    """A lease with sensible defaults. Pass ``tenants`` to attach them in order."""
    if unit is None:
        unit = make_unit()
    start = start_date or timezone.localdate()
    end = end_date or (start + dt.timedelta(days=365))
    lease = Lease.objects.create(
        unit=unit,
        start_date=start,
        end_date=end,
        monthly_rent=monthly_rent,
        deposit=deposit,
        rent_due_day=rent_due_day,
        status=status,
        **fields,
    )
    for index, tenant in enumerate(tenants):
        LeaseTenant.objects.create(lease=lease, tenant=tenant, is_primary=index == 0)
    return lease


# --- Accounting -----------------------------------------------------------


def make_charge(
    lease: Lease | None = None,
    *,
    amount: Decimal = Decimal("1850.00"),
    due_date=None,
    kind: str = ChargeKind.RENT,
    direction: str = Direction.INCREASE,
    description: str = "Rent",
    **fields,
) -> Charge:
    """A ledger charge. A lease is created when none is given."""
    if lease is None:
        lease = make_lease()
    return Charge.objects.create(
        lease=lease,
        kind=kind,
        direction=direction,
        description=description,
        amount=amount,
        due_date=due_date or timezone.localdate(),
        **fields,
    )


def make_payment(
    lease: Lease | None = None,
    *,
    amount: Decimal = Decimal("1850.00"),
    payment_date=None,
    method: str = PaymentMethod.ACH,
    status: str = PaymentStatus.CLEARED,
    **fields,
) -> Payment:
    """A recorded payment. Cleared by default, because that is the common case."""
    if lease is None:
        lease = make_lease()
    return Payment.objects.create(
        lease=lease,
        amount=amount,
        payment_date=payment_date or timezone.localdate(),
        method=method,
        status=status,
        **fields,
    )
