"""The tenant's dashboard: their five questions on one page.

Three of the five are answerable from real data today (what is owed, when it is
due, where the lease is); maintenance and announcements belong to Phases 7 and 8,
and the page labels them rather than showing a button that goes nowhere.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from apps.leases.models import LeaseStatus
from apps.ledger.models import PaymentStatus
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_maintenance,
    make_manager,
    make_payment,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def dashboard():
    return reverse("accounts:home")


def test_a_tenant_lands_on_the_dashboard(client, dashboard):
    tenant = make_tenant(username="ada", first_name="Ada")
    make_lease(make_unit(identifier="Storefront"), tenants=[tenant])
    client.force_login(tenant)

    response = client.get(dashboard)
    body = response.content.decode()

    assert response.status_code == 200
    assert "Storefront" in body
    assert "Your home" not in body


def test_the_banner_shows_the_unit_and_the_property(client, dashboard):
    """Facts, not a greeting: the banner says where the tenant is, nothing more."""
    tenant = make_tenant(username="ada", first_name="Ada")
    make_lease(make_unit(identifier="Austin/Ruiming"), tenants=[tenant])
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "Austin/Ruiming" in body
    assert "Test Property" in body or "Maple Street Duplex" in body


def test_the_portal_does_not_greet_or_thank(client, dashboard):
    tenant = make_tenant(username="ada", first_name="Ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("200.00"), payment_date=TODAY)
    client.force_login(tenant)

    for url in (dashboard, reverse("payments:home"), reverse("tenancy:lease")):
        body = client.get(url).content.decode()
        for phrase in ("Good morning", "Good afternoon", "Good evening", "Your home", "thank you"):
            assert phrase not in body, f"{phrase!r} should not appear on {url}"


def test_the_three_cards_carry_the_derived_figures(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant], monthly_rent=Decimal("1850.00"))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY - dt.timedelta(days=3))
    make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "Due now" in body
    assert "1,350.00" in body, "the figure is derived, and part-paid is shown as such"
    assert "past due" in body, "the card says how much of it is late"
    assert "Next rent due" in body
    assert "Lease ends" in body
    # Dates render in the US format the rest of the portal uses.
    assert date_format(lease.end_date) in body
    assert "1,850.00" in body


def test_a_tenant_paid_ahead_sees_credit_not_debt(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant], monthly_rent=Decimal("1000.00"))
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("12000.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "in credit" in body
    assert "11,000.00" in body, "the year's prepayment shows as credit, not as a debt"
    assert "$0.00" not in body, "a settled month is never dressed up as a demand"


def test_a_settled_tenancy_says_nothing_is_owing(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "Nothing due" in body
    assert "nothing is owing" in body


def test_the_recent_activity_nets_an_adjustment(client, dashboard):
    """One line at $0.00, not a charge and its credit brawling on the page."""
    from apps.ledger import services
    from apps.ledger.models import Direction

    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    charge = make_charge(lease, amount=Decimal("2084.00"), due_date=TODAY)
    services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("2084.00"), reason="raised in error"
    )
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "was $2,084.00, adjusted" in body
    assert "−$2,084.00" not in body, "the correction is not a second line"


def test_the_recent_activity_and_quick_actions_are_real(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("950.00"), due_date=TODAY, description="Rent for this month")
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "Recent activity" in body
    assert "Rent for this month" in body
    assert reverse("tenancy:lease") in body
    assert reverse("payments:home") in body
    assert reverse("accounts:profile") in body


def test_the_two_later_panels_are_labelled_not_faked(client, dashboard):
    tenant = make_tenant(username="ada")
    make_lease(tenants=[tenant])
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "Maintenance" in body and "Phase 7" in body
    assert "Announcements" in body and "Phase 8" in body
    assert "Maintenance Request" not in body, "no button that goes nowhere"


def test_a_tenant_with_no_lease_is_told_so(client, dashboard):
    client.force_login(make_tenant(username="newcomer"))

    body = client.get(dashboard).content.decode()

    assert "No lease yet" in body
    assert "Current balance" not in body
    assert "0.00" not in body, "no zero dressed up as a fact"


def test_a_draft_lease_is_not_shown(client, dashboard):
    tenant = make_tenant(username="ada")
    make_lease(tenants=[tenant], status=LeaseStatus.DRAFT)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "No lease yet" in body


def test_a_lease_ending_soon_says_how_soon(client, dashboard):
    tenant = make_tenant(username="ada")
    make_lease(
        tenants=[tenant],
        start_date=TODAY - dt.timedelta(days=300),
        end_date=TODAY + dt.timedelta(days=20),
    )
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "in 20 days" in body


def test_an_ended_lease_still_shows_what_is_owed(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(
        tenants=[tenant],
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=60))
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "100.00" in body
    assert "this lease has ended" in body


def test_an_expected_payment_is_shown_without_moving_the_balance(client, dashboard):
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY, status=PaymentStatus.PENDING)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "1,000.00" in body, "expected money is not money"
    assert "Payment expected" in body, "a promise is labelled as one"


def test_two_tenants_never_see_each_others_money(client, dashboard):
    mine = make_tenant(username="ada", first_name="Ada")
    theirs = make_tenant(username="bob", first_name="Bob")
    my_lease = make_lease(tenants=[mine])
    their_lease = make_lease(tenants=[theirs])
    make_charge(my_lease, amount=Decimal("111.00"), due_date=TODAY, description="Mine only")
    make_charge(their_lease, amount=Decimal("999.00"), due_date=TODAY, description="Theirs only")

    client.force_login(mine)
    body = client.get(dashboard).content.decode()
    assert "Mine only" in body
    assert "Theirs only" not in body
    assert "999.00" not in body

    client.force_login(theirs)
    their_body = client.get(dashboard).content.decode()
    assert "Theirs only" in their_body
    assert "Mine only" not in their_body


@pytest.mark.parametrize(
    "maker", [make_manager, make_admin, make_maintenance], ids=["manager", "admin", "maintenance"]
)
def test_staff_are_sent_to_the_management_area(client, dashboard, maker):
    """The landing is role-aware: staff are not shown a 403 for a page they were
    redirected to."""
    client.force_login(maker(username="staff-member"))

    response = client.get(dashboard)

    assert response.status_code == 302
    assert response["Location"] == reverse("manage:home")


def test_anonymous_visitors_are_sent_to_sign_in(client, dashboard):
    response = client.get(dashboard)

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_the_dashboard_is_built_for_a_phone(client, dashboard):
    """The specification's acceptance criteria are about phone width, so the
    structure is asserted even though the final check is the owner's own phone."""
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "grid gap-4 sm:grid-cols-2 lg:grid-cols-3" in body, "single column on a phone"
    assert "w-full sm:w-auto" in body, "full-width buttons to tap"
    assert "<table" not in body, "no wide table in the tenant's path"
    assert 'name="viewport"' in body


def test_the_dashboard_does_not_leak_the_audit_trail(client, dashboard):
    """A tenant sees their money, not the office's internal notes about it."""
    tenant = make_tenant(username="ada")
    lease = make_lease(tenants=[tenant])
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    client.force_login(tenant)

    body = client.get(dashboard).content.decode()

    assert "History" not in body
    assert "audit" not in body.lower()
