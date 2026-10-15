"""E4: bringing a live tenancy into RHP without inventing a debt.

The failing case these tests exist for: a lease that began years ago, activated and
charged the ordinary way, produced 108 charges and a $100,536 "balance" for a tenant
who is paid up. The guard below makes that impossible; the two onboarding methods
place the tenancy truthfully; and a stated schedule lets the office record the
amounts the paper actually names.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.leases.models import (
    LeaseOnboarding,
    LeaseTemplate,
    OnboardingMethod,
    RentPeriodOrigin,
)
from apps.ledger import services as ledger_services
from apps.ledger.models import ChargeKind
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_manager,
    make_nnn_rate,
    make_tenant,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()

#: Michael Ortolano's live lease shape: 60 months from June 2022, six stated amounts,
#: NNN adjusted each October. The dates are absolute because the lease is.
MICHAEL_SCHEDULE = [
    (dt.date(2022, 6, 1), "1450.00"),
    (dt.date(2023, 6, 1), "1508.00"),
    (dt.date(2023, 11, 1), "1852.00"),  # Extra Space, mid-year
    (dt.date(2024, 6, 1), "1925.00"),
    (dt.date(2025, 6, 1), "2002.00"),
    (dt.date(2026, 6, 1), "2113.00"),
]


def a_live_tenancy(**fields):
    """A tenancy that began years ago and has not been placed in RHP yet."""
    fields.setdefault("start_date", dt.date(2022, 6, 1))
    fields.setdefault("end_date", dt.date(2027, 5, 30))
    fields.setdefault("monthly_rent", Decimal("1450.00"))
    fields.setdefault("rent_due_day", 1)
    fields.setdefault("template", LeaseTemplate.NNN)
    fields.setdefault("step_up_month", None)
    fields.setdefault("billing_start_date", None)
    return make_lease(**fields)


# --- the guard ------------------------------------------------------------


def test_a_tenancy_from_before_this_month_cannot_be_charged_yet():
    lease = a_live_tenancy()

    assert lease.needs_onboarding is True

    with pytest.raises(ValidationError, match="has not been brought into RHP yet"):
        ledger_services.generate_charges(lease, through=TODAY)

    assert not lease.charges.exists(), "nothing was raised"


def test_a_tenancy_that_began_this_month_is_charged_as_always():
    lease = make_lease(start_date=TODAY.replace(day=1), rent_due_day=1)
    del lease.billing_start_date  # the factory marks it placed; this one never needed placing

    assert lease.needs_onboarding is False
    ledger_services.generate_charges(lease, through=TODAY)
    assert lease.charges.count() == 1


def test_the_cutover_is_what_unlocks_charging():
    lease = a_live_tenancy(billing_start_date=dt.date(2026, 1, 1))

    ledger_services.generate_charges(lease, through=dt.date(2026, 2, 28))

    assert [c.due_date for c in lease.charges.order_by("due_date")] == [
        dt.date(2026, 1, 1),
        dt.date(2026, 2, 1),
    ], "billed from the cutover, not from the term's start"


# --- method A: raise the history, bring in what was received --------------


def test_history_onboarding_leaves_the_true_position():
    lease = a_live_tenancy()
    for effective_from, amount in MICHAEL_SCHEDULE:
        lease_services.add_rent_period(lease, effective_from=effective_from, amount=Decimal(amount))
    # NNN at $305 a month, as the 2022 estimate says, staged from the term's start.
    make_nnn_rate(lease, effective_from=dt.date(2022, 6, 1), monthly_amount=Decimal("305.00"))

    # Paid up apart from the last couple of months, which is what a healthy live
    # tenancy looks like — not a tenant who has paid nothing for four years.
    onboarding = lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.HISTORY,
        as_of=TODAY,
        received_total=Decimal("108000.00"),
        through=TODAY,
        note="Paid by bank transfer since 2022",
    )

    lease.refresh_from_db()
    ledger = ledger_services.build_ledger(lease)
    charged = sum((c.amount for c in lease.charges.all()), Decimal("0.00"))
    received = sum((p.amount for p in lease.payments.all()), Decimal("0.00"))

    assert onboarding.method == OnboardingMethod.HISTORY
    assert lease.billing_start_date == lease.start_date, "the whole term is billed"
    assert received == Decimal("108000.00")
    assert charged > Decimal("100000.00"), "the whole term's history is there"
    assert ledger.balance_due == charged - received, "the payment settled the oldest months"
    assert Decimal("0.00") <= ledger.balance_due < Decimal("6000.00"), (
        "a couple of months, not a hundred grand"
    )
    assert ledger.arrears < Decimal("6000.00"), "the arrears are the same truth"


def test_history_onboarding_bills_the_amounts_the_lease_states():
    lease = a_live_tenancy()
    for effective_from, amount in MICHAEL_SCHEDULE:
        lease_services.add_rent_period(lease, effective_from=effective_from, amount=Decimal(amount))

    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.HISTORY,
        as_of=TODAY,
        received_total=Decimal("0.00"),
        through=dt.date(2026, 8, 1),
    )

    by_date = {c.due_date: c.amount for c in lease.charges.filter(kind=ChargeKind.RENT)}
    assert by_date[dt.date(2022, 6, 1)] == Decimal("1450.00")
    assert by_date[dt.date(2023, 10, 1)] == Decimal("1508.00")
    assert by_date[dt.date(2023, 11, 1)] == Decimal("1852.00"), "the Extra Space month"
    assert by_date[dt.date(2026, 6, 1)] == Decimal("2113.00"), "the last stated amount"


def test_onboarding_refuses_a_lease_that_already_has_charges():
    lease = a_live_tenancy(billing_start_date=dt.date(2022, 6, 1))
    make_charge(lease, amount=Decimal("10.00"), due_date=dt.date(2022, 6, 1))

    with pytest.raises(ValidationError, match="already has charges"):
        lease_services.onboard_lease(
            lease, method=OnboardingMethod.HISTORY, as_of=TODAY, received_total=Decimal("0")
        )


def test_onboarding_refuses_a_tenancy_that_started_this_month():
    lease = make_lease(start_date=TODAY.replace(day=1), billing_start_date=None)

    with pytest.raises(ValidationError, match="ordinary way"):
        lease_services.onboard_lease(
            lease, method=OnboardingMethod.HISTORY, as_of=TODAY, received_total=Decimal("0")
        )


def test_onboarding_refuses_a_draft():
    lease = a_live_tenancy(billing_start_date=None)
    lease.status = "DRAFT"
    lease.save(update_fields=["status"])

    with pytest.raises(ValidationError, match="Activate the lease first"):
        lease_services.onboard_lease(
            lease, method=OnboardingMethod.HISTORY, as_of=TODAY, received_total=Decimal("0")
        )


# --- method B: start at a date and state the position --------------------


def test_position_onboarding_brings_a_balance_forward():
    lease = a_live_tenancy()

    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.POSITION,
        as_of=TODAY,
        opening_amount=Decimal("1450.00"),
        billing_start_date=TODAY.replace(day=1),
        note="One month behind at cutover",
    )

    lease.refresh_from_db()
    ledger = ledger_services.build_ledger(lease)
    opening = lease.charges.get(kind=ChargeKind.OPENING)

    assert lease.billing_start_date == TODAY.replace(day=1)
    assert opening.description == "Balance brought forward"
    assert opening.amount == Decimal("1450.00")
    assert ledger.balance_due == Decimal("1450.00")
    assert not lease.charges.filter(kind=ChargeKind.RENT).exists(), "the past is not billed"


def test_position_onboarding_brings_a_credit_forward():
    lease = a_live_tenancy()

    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.POSITION,
        as_of=TODAY,
        opening_amount=Decimal("-2000.00"),
        billing_start_date=TODAY.replace(day=1),
        note="Paid two months ahead",
    )

    lease.refresh_from_db()
    ledger = ledger_services.build_ledger(lease)

    assert ledger.balance_due == Decimal("-2000.00"), "money on account, not a debt"
    assert ledger.credit == Decimal("2000.00")
    assert not lease.charges.exists(), "a credit is not a charge"


def test_position_onboarding_can_say_exactly_square():
    lease = a_live_tenancy()

    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.POSITION,
        as_of=TODAY,
        opening_amount=Decimal("0.00"),
        billing_start_date=TODAY.replace(day=1),
    )

    ledger = ledger_services.build_ledger(lease)
    assert ledger.balance_due == Decimal("0.00")
    assert not lease.charges.exists() and not lease.payments.exists()


def test_position_onboarding_refuses_a_cutover_outside_the_term():
    lease = a_live_tenancy()

    with pytest.raises(ValidationError, match="inside the term"):
        lease_services.onboard_lease(
            lease,
            method=OnboardingMethod.POSITION,
            as_of=TODAY,
            opening_amount=Decimal("0.00"),
            billing_start_date=dt.date(2021, 1, 1),
        )


def test_the_onboarding_record_says_how_the_tenancy_was_placed():
    lease = a_live_tenancy()

    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.POSITION,
        as_of=TODAY,
        opening_amount=Decimal("100.00"),
        billing_start_date=TODAY.replace(day=1),
        note="Taken over from the previous manager",
    )

    onboarding = LeaseOnboarding.objects.get(lease=lease)
    assert onboarding.note == "Taken over from the previous manager"
    assert lease.has_onboarding is True
    assert AuditEvent.objects.filter(action=AuditAction.LEASE_ONBOARDED, lease=lease).exists()


# --- a stated schedule the office owns ------------------------------------


def test_a_stated_lease_keeps_the_amounts_the_office_entered():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=dt.date(2022, 6, 1))
    for effective_from, amount in MICHAEL_SCHEDULE:
        lease_services.add_rent_period(lease, effective_from=effective_from, amount=Decimal(amount))

    result = lease_services.generate_rent_schedule(lease)

    assert result.created == [] and result.removed == []
    assert lease.rent_periods.count() == len(MICHAEL_SCHEDULE)
    assert lease.rent_for(dt.date(2023, 11, 1)) == Decimal("1852.00")


def test_a_hand_set_period_survives_regenerating_a_stepped_schedule():
    """The defect E4 fixes: a rule cannot plan a mid-year change, so it must not delete it."""
    lease = make_lease(
        start_date=dt.date(2027, 1, 1),
        end_date=dt.date(2030, 12, 31),
        rent_due_day=5,
        template=LeaseTemplate.STEP_UP,
        step_up_month=6,
        step_up_percent=Decimal("4.00"),
    )
    lease_services.generate_rent_schedule(lease)
    extra = lease_services.add_rent_period(
        lease,
        effective_from=dt.date(2027, 11, 5),
        amount=Decimal("1852.00"),
        note="Extra space taken",
    )

    result = lease_services.generate_rent_schedule(lease)

    extra.refresh_from_db()
    assert extra.amount == Decimal("1852.00")
    assert extra.origin == RentPeriodOrigin.MANUAL
    assert dt.date(2027, 11, 5) not in result.removed
    assert lease.rent_periods.filter(effective_from=dt.date(2027, 11, 5)).exists()


def test_a_stated_amount_must_fall_on_a_rent_due_date_inside_the_term():
    lease = a_live_tenancy(template=LeaseTemplate.STATED)

    with pytest.raises(ValidationError):
        lease_services.add_rent_period(
            lease, effective_from=dt.date(2022, 6, 7), amount=Decimal("1450.00")
        )

    with pytest.raises(ValidationError):
        lease_services.add_rent_period(
            lease, effective_from=dt.date(2030, 6, 1), amount=Decimal("1450.00")
        )


def test_a_fixed_lease_has_nothing_to_state():
    lease = make_lease(template=LeaseTemplate.FIXED, start_date=TODAY, billing_start_date=None)

    with pytest.raises(ValidationError, match="one rent for its term"):
        lease_services.add_rent_period(
            lease, effective_from=TODAY.replace(day=1), amount=Decimal("100.00")
        )


def test_a_stated_amount_can_be_removed_while_nothing_is_charged():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)
    period = lease_services.add_rent_period(
        lease, effective_from=dt.date(2022, 6, 1), amount=Decimal("1450.00")
    )

    lease_services.remove_rent_period(period)

    assert not lease.rent_periods.exists()


def test_a_charged_amount_cannot_be_removed():
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=dt.date(2022, 6, 1))
    period = lease_services.add_rent_period(
        lease, effective_from=dt.date(2022, 6, 1), amount=Decimal("1450.00")
    )
    ledger_services.generate_charges(lease, through=dt.date(2022, 6, 30))

    with pytest.raises(ValidationError, match="already been charged"):
        lease_services.remove_rent_period(period)


# --- the screens ----------------------------------------------------------


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="onboarding-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="onboarding-manager"))
    return client


def test_the_lease_page_asks_for_the_history_to_be_placed(as_admin):
    lease = a_live_tenancy()

    body = " ".join(
        strip_tags(
            as_admin.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()
        ).split()
    )

    assert "Bring this tenancy into RHP" in body
    assert "has not been brought into RHP" in body


def test_an_admin_places_the_history_through_the_screen(as_admin):
    lease = a_live_tenancy()

    response = as_admin.post(
        reverse("leases:onboard", args=[lease.pk]),
        {
            "method": OnboardingMethod.HISTORY,
            "as_of": TODAY.isoformat(),
            "received_total": "60000.00",
            "opening_amount": "",
            "billing_start_date": lease.start_date.isoformat(),
            "note": "Bank transfers since 2022",
        },
    )

    assert response.status_code == 302
    lease.refresh_from_db()
    assert lease.billing_start_date == lease.start_date
    assert lease.payments.count() == 1
    assert lease.charges.exists()


def test_an_admin_states_a_rent_amount_through_the_screen(as_admin):
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)

    response = as_admin.post(
        reverse("leases:rent-period-create", args=[lease.pk]),
        {"effective_from": "2022-06-01", "amount": "1450.00", "note": "As the lease states"},
    )

    assert response.status_code == 302
    period = lease.rent_periods.get()
    assert period.amount == Decimal("1450.00")
    assert period.origin == RentPeriodOrigin.MANUAL


def test_a_manager_cannot_place_a_history_or_state_an_amount(as_manager):
    lease = a_live_tenancy(template=LeaseTemplate.STATED, billing_start_date=None)

    assert as_manager.get(reverse("leases:onboard", args=[lease.pk])).status_code == 403
    assert (
        as_manager.post(
            reverse("leases:rent-period-create", args=[lease.pk]),
            {"effective_from": "2022-06-01", "amount": "1450.00", "note": ""},
        ).status_code
        == 403
    )


def test_a_tenant_never_reaches_the_onboarding_screen(client):
    lease = a_live_tenancy()
    client.force_login(make_tenant(username="ada"))

    assert client.get(reverse("leases:onboard", args=[lease.pk])).status_code == 403


def test_the_ledger_says_why_it_will_not_charge(as_manager):
    lease = a_live_tenancy()

    response = as_manager.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    body = " ".join(strip_tags(response.content.decode()).split())
    assert "has not been brought into RHP yet" in body
    assert not lease.charges.exists()


def test_the_tenant_statement_shows_a_brought_forward_balance(client):
    tenant = make_tenant(username="ada")
    lease = a_live_tenancy(tenants=[tenant], billing_start_date=None)
    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.POSITION,
        as_of=TODAY.replace(day=1),
        opening_amount=Decimal("1450.00"),
        billing_start_date=TODAY.replace(day=1),
    )
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("payments:home")).content.decode()).split())

    assert "Balance brought forward" in body
    assert "$1,450.00" in body


def test_the_tenant_statement_shows_a_stated_history_with_its_nnn(client):
    """What the tenant of a stated, NNN-carrying lease reads after being brought in.

    The whole point of raising the history is that the tenant can see it: each month
    they were billed, rent and NNN apart, and the money they had already paid.
    """
    tenant = make_tenant(username="ada")
    lease = a_live_tenancy(tenants=[tenant], template=LeaseTemplate.STATED, carries_nnn=True)
    for effective_from, amount in MICHAEL_SCHEDULE:
        lease_services.add_rent_period(lease, effective_from=effective_from, amount=Decimal(amount))
    lease_services.stage_nnn_rate(
        lease, effective_from=dt.date(2022, 6, 1), monthly_amount=Decimal("305.00")
    )
    lease_services.onboard_lease(
        lease,
        method=OnboardingMethod.HISTORY,
        as_of=TODAY,
        received_total=Decimal("108000.00"),
        billing_start_date=dt.date(2022, 6, 1),
    )
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("payments:home")).content.decode()).split())

    assert "months and payments" in body
    assert "rent and charges" in body, "the history is listed month by month"
    assert "NNN" in body and "$305.00" in body, "the NNN they paid is shown apart from rent"
    assert "Payment received" in body and "$108,000.00" in body
