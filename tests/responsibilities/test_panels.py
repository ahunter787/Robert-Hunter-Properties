"""E2 screens: the property's responsibilities, and the month card a tenant reads.

Viewing a property's bills is a manager's business; staging them and setting what a
unit pays is an admin's, because those figures become charges (ADR-014).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.ledger import services as ledger_services
from apps.responsibilities import services
from apps.responsibilities.models import ResponsibilityCategory
from tests.factories import (
    make_admin,
    make_charge,
    make_cycle,
    make_lease,
    make_manager,
    make_nnn_rate,
    make_property,
    make_responsibility,
    make_share,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="responsibility-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="responsibility-manager"))
    return client


def billed_building():
    """Two units, 76/24 by size, one quarterly water bill staged."""
    property_obj = make_property(name="Billed Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=240)
    responsibility = make_responsibility(property_obj, label="Water")
    cycle = make_cycle(
        responsibility,
        starts_on=TODAY.replace(day=1),
        months=3,
        total_amount=Decimal("600.00"),
    )
    make_share(cycle, first, monthly_amount=Decimal("152.00"))
    make_share(cycle, second, monthly_amount=Decimal("48.00"))
    return property_obj, first, second, responsibility, cycle


def text_of(response) -> str:
    return " ".join(strip_tags(response.content.decode()).split())


# --- the property screen --------------------------------------------------


def test_a_manager_reads_the_property_bills(as_manager):
    property_obj, _first, _second, _responsibility, _cycle = billed_building()

    body = text_of(as_manager.get(reverse("portfolio:property-detail", args=[property_obj.pk])))

    assert "Responsibilities" in body
    assert "Water" in body
    assert "$600.00" in body
    assert "$200.00 a month to divide" in body
    assert "76.00%" in body and "24.00%" in body
    assert "$152.00" in body and "$48.00" in body
    assert "Stage the next bill" not in body, "staging is an admin's act"
    assert "Add a responsibility" not in body


def test_the_card_says_what_the_landlord_carries(as_admin):
    property_obj, first, _second, responsibility, cycle = billed_building()
    services.set_shares(cycle, {first.pk: Decimal("80.00")})

    body = text_of(as_admin.get(reverse("portfolio:property-detail", args=[property_obj.pk])))

    assert "$120.00 a month of this bill is not carried by a unit." in body
    assert "no lease: the landlord carries it" in body


def test_the_card_says_when_nothing_is_staged(as_admin):
    property_obj = make_property(name="Unstaged")
    make_unit(for_property=property_obj, identifier="1", square_feet=500)
    make_responsibility(property_obj, label="Trash")

    body = text_of(as_admin.get(reverse("portfolio:property-detail", args=[property_obj.pk])))

    assert "No cycle staged yet, so nothing is being charged." in body


def test_a_manager_cannot_reach_the_admin_screens(as_manager):
    _property_obj, _first, _second, responsibility, cycle = billed_building()

    assert (
        as_manager.get(
            reverse("responsibilities:cycle-stage", args=[responsibility.pk])
        ).status_code
        == 403
    )
    assert (
        as_manager.get(reverse("responsibilities:cycle-shares", args=[cycle.pk])).status_code == 403
    )
    assert (
        as_manager.get(
            reverse("responsibilities:responsibility-update", args=[responsibility.pk])
        ).status_code
        == 403
    )


def test_a_tenant_never_reaches_them(client):
    property_obj, _first, _second, responsibility, cycle = billed_building()
    client.force_login(make_tenant(username="ada"))

    assert (
        client.get(reverse("responsibilities:cycle-stage", args=[responsibility.pk])).status_code
        == 403
    )
    assert (
        client.post(
            reverse("responsibilities:responsibility-create", args=[property_obj.pk]), {}
        ).status_code
        == 403
    )


# --- adding and staging ---------------------------------------------------


def test_an_admin_adds_a_responsibility(as_admin):
    property_obj = make_property(name="Adding Building")
    make_unit(for_property=property_obj, identifier="1", square_feet=500)

    response = as_admin.post(
        reverse("responsibilities:responsibility-create", args=[property_obj.pk]),
        {
            "label": "Trash",
            "category": ResponsibilityCategory.UTILITY,
            "cycle_months": "3",
            "is_active": "on",
            "note": "",
        },
    )

    assert response.status_code == 302
    responsibility = property_obj.responsibilities.get()
    assert responsibility.label == "Trash"
    assert AuditEvent.objects.filter(action=AuditAction.RESPONSIBILITY_CHANGED).exists()


def test_staging_proposes_the_shares_from_the_sizes(as_admin):
    property_obj = make_property(name="Staging Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=240)
    responsibility = make_responsibility(property_obj, label="Water")

    response = as_admin.post(
        reverse("responsibilities:cycle-stage", args=[responsibility.pk]),
        {
            "starts_on": TODAY.replace(day=1).isoformat(),
            "months": "3",
            "total_amount": "600.00",
            "note": "City of Springfield",
            f"unit_{first.pk}": "",
            f"unit_{second.pk}": "",
        },
    )

    assert response.status_code == 302
    cycle = responsibility.cycles.get()
    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares[first.pk] == Decimal("152.00")
    assert shares[second.pk] == Decimal("48.00")
    assert AuditEvent.objects.filter(action=AuditAction.RESPONSIBILITY_CYCLE_STAGED).exists()


def test_a_typed_amount_beats_the_proposal(as_admin):
    property_obj = make_property(name="Override Building")
    first = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    second = make_unit(for_property=property_obj, identifier="2", square_feet=240)
    responsibility = make_responsibility(property_obj, label="Water")

    as_admin.post(
        reverse("responsibilities:cycle-stage", args=[responsibility.pk]),
        {
            "starts_on": TODAY.replace(day=1).isoformat(),
            "months": "3",
            "total_amount": "600.00",
            "note": "",
            f"unit_{first.pk}": "80.00",
            f"unit_{second.pk}": "",
        },
    )

    cycle = responsibility.cycles.get()
    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares[first.pk] == Decimal("80.00"), "the amount the office typed wins"
    assert shares[second.pk] == Decimal("48.00"), "the unit it left blank keeps its size share"

    # What the units carry is shown against the bill rather than quietly made to fit.
    body = text_of(as_admin.get(reverse("portfolio:property-detail", args=[property_obj.pk])))
    assert "$72.00 a month of this bill is not carried by a unit." in body


def test_a_staged_cycle_can_be_re_aimed_at_the_units(as_admin):
    property_obj, first, second, responsibility, cycle = billed_building()
    del property_obj

    response = as_admin.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]),
        {
            f"unit_{first.pk}": "300.00",
            f"unit_{second.pk}": "0.00",
            "note": "usage-based",
        },
    )

    assert response.status_code == 302
    shares = {share.unit_id: share.monthly_amount for share in cycle.shares.all()}
    assert shares == {first.pk: Decimal("300.00")}
    assert AuditEvent.objects.filter(action=AuditAction.RESPONSIBILITY_SHARES_SET).exists()


def test_a_charged_cycle_refuses_the_change_out_loud(as_admin):
    _property_obj, first, second, responsibility, cycle = billed_building()
    lease = make_lease(
        first,
        start_date=TODAY.replace(day=1) - dt.timedelta(days=10),
        end_date=TODAY + dt.timedelta(days=200),
        rent_due_day=1,
        monthly_rent=Decimal("1000.00"),
    )
    ledger_services.generate_charges(lease, through=ledger_services.generation_horizon(1))

    response = as_admin.post(
        reverse("responsibilities:cycle-shares", args=[cycle.pk]),
        {
            f"unit_{first.pk}": "10.00",
            f"unit_{second.pk}": "10.00",
            "note": "too late",
        },
    )

    assert response.status_code == 200, "the refusal is shown, not swallowed"
    assert "already been charged" in text_of(response)
    assert cycle.shares.get(unit=first).monthly_amount == Decimal("152.00")

    unused = responsibility.cycles.count()
    assert unused == 1


def test_stopping_a_responsibility_leaves_its_history(as_admin):
    _property_obj, _first, _second, responsibility, _cycle = billed_building()

    as_admin.post(
        reverse("responsibilities:responsibility-update", args=[responsibility.pk]),
        {
            "label": responsibility.label,
            "category": responsibility.category,
            "cycle_months": str(responsibility.cycle_months),
            "note": "",
            # is_active unchecked: stopped
        },
    )

    responsibility.refresh_from_db()
    assert responsibility.is_active is False
    assert responsibility.cycles.count() == 1


# --- the month card -------------------------------------------------------


def a_full_month(client, *, with_tenant=True):
    """One tenancy charged rent, NNN and two responsibilities on the same date."""
    due = TODAY.replace(day=1)
    property_obj = make_property(name="Month Card Building")
    unit = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    tenant = make_tenant(username="ada") if with_tenant else None
    lease = make_lease(
        unit,
        tenants=[tenant] if tenant else [],
        template="NNN",
        step_up_month=1,
        step_up_percent=Decimal("0.00"),
        monthly_rent=Decimal("1000.00"),
        rent_due_day=1,
        start_date=due,
        end_date=TODAY + dt.timedelta(days=400),
    )
    make_nnn_rate(lease, effective_from=due, monthly_amount=Decimal("200.00"))
    water = make_responsibility(property_obj, label="Water")
    water_cycle = make_cycle(water, starts_on=due, months=3, total_amount=Decimal("300.00"))
    make_share(water_cycle, unit, monthly_amount=Decimal("100.00"))
    pruning = make_responsibility(
        property_obj, label="Pruning", category=ResponsibilityCategory.MAINTENANCE
    )
    pruning_cycle = make_cycle(pruning, starts_on=due, months=3, total_amount=Decimal("144.00"))
    make_share(pruning_cycle, unit, monthly_amount=Decimal("48.00"))
    ledger_services.generate_charges(lease, through=due)
    return lease, tenant, due


def test_the_tenant_month_card_groups_the_charges(client):
    _lease, tenant, due = a_full_month(client)
    client.force_login(tenant)

    body = text_of(client.get(reverse("payments:home")))

    assert f"{due:%B %Y}" in body
    assert "rent and charges" in body
    assert "$1,348.00" in body, "1000 rent + 200 NNN + 100 water + 48 pruning"
    assert "Base rent" in body and "$1,000.00" in body
    assert "NNN" in body and "$200.00" in body
    assert "Utility" in body and "$100.00" in body
    assert "Maintenance" in body and "$48.00" in body
    assert "Water" in body and "Pruning" in body
    assert "<details" in client.get(reverse("payments:home")).content.decode()


def test_a_month_counts_as_one_statement_entry(client):
    lease, tenant, due = a_full_month(client)
    client.force_login(tenant)

    response = client.get(reverse("payments:home"))

    assert response.context["statement_total"] == 1, "four charges, one month"
    assert len(response.context["statement"]) == 1
    assert lease.charges.count() == 4


def test_the_dashboard_shows_the_month_not_four_rows(client):
    _lease, tenant, _due = a_full_month(client)
    client.force_login(tenant)

    body = text_of(client.get(reverse("accounts:home")))

    assert "Recent activity" in body
    assert "rent and charges" in body


def test_a_partly_paid_month_says_what_is_left(client):
    _lease, tenant, due = a_full_month(client)
    ledger_services.record_payment(_lease, amount=Decimal("500.00"), payment_date=due, method="ACH")
    client.force_login(tenant)

    body = text_of(client.get(reverse("payments:home")))

    assert "$500.00 to pay" in body, "the rent that the payment part settled"
    assert "$848.00 of this month is still to pay." in body


def test_the_lease_page_notes_the_next_step_up(client):
    property_obj = make_property(name="Note Building")
    unit = make_unit(for_property=property_obj, identifier="1", square_feet=500)
    tenant = make_tenant(username="ada")
    lease = make_lease(
        unit,
        tenants=[tenant],
        template="STEP_UP",
        step_up_month=(TODAY.month % 12) + 1,
        step_up_percent=Decimal("5.00"),
        monthly_rent=Decimal("1000.00"),
        rent_due_day=1,
        start_date=TODAY.replace(day=1),
        end_date=TODAY + dt.timedelta(days=400),
    )
    from apps.leases import services as lease_services

    lease_services.generate_rent_schedule(lease)
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY.replace(day=1))
    client.force_login(tenant)

    body = text_of(client.get(reverse("payments:home")))

    assert "steps up in 1 month" in body


def test_the_next_rent_due_figure_still_separates_nnn(client):
    lease, tenant, _due = a_full_month(client)
    client.force_login(tenant)

    body = text_of(client.get(reverse("payments:home")))

    assert "plus NNN" in body
    assert date_format(ledger_services.upcoming_rent_date(lease)) in body


def test_the_cam_rate_is_reference_only(as_admin):
    """CAM is folded into base rent, per the owner's document: shown, never charged."""
    from apps.ledger.models import Charge

    property_obj = make_property(name="CAM Building", cam_rate_per_sqft=Decimal("0.20"))
    unit = make_unit(for_property=property_obj, identifier="1", square_feet=760)
    lease = make_lease(
        unit, start_date=TODAY.replace(day=1), end_date=TODAY + dt.timedelta(days=200)
    )

    body = text_of(as_admin.get(reverse("portfolio:property-detail", args=[property_obj.pk])))
    ledger_services.generate_charges(lease, through=ledger_services.generation_horizon(1))

    assert "CAM $0.20 a square foot" in body
    assert "760 sq ft recorded" in body
    assert not Charge.objects.filter(lease=lease, kind="RESPONSIBILITY").exists(), (
        "CAM never becomes a charge of its own"
    )
