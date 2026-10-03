"""E1: the three lease templates, the rent schedule, and the NNN amount.

The point of these tests is that the money for every month is decided once and
then never re-derived: a stepped lease works its term out at the start, a
triple-net month carries its rent and its NNN, and anything already charged is
left exactly as it was, because a charge is corrected with an adjustment
(ADR-008, ADR-013).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.leases.models import LeaseStatus, LeaseTemplate, RentPeriodOrigin
from apps.ledger import services as ledger_services
from apps.ledger.models import ChargeKind
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_manager,
    make_nnn_rate,
    make_rent_period,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def stepped_lease(**fields):
    """A worked four-year step-up: $2,084 rising 7% each September."""
    fields.setdefault("template", LeaseTemplate.STEP_UP)
    fields.setdefault("step_up_month", 9)
    fields.setdefault("step_up_percent", Decimal("7.00"))
    fields.setdefault("start_date", dt.date(2027, 1, 1))
    fields.setdefault("end_date", dt.date(2030, 12, 31))
    fields.setdefault("monthly_rent", Decimal("2084.00"))
    fields.setdefault("rent_due_day", 5)
    return make_lease(**fields)


def nnn_lease(**fields):
    fields.setdefault("step_up_month", 1)
    fields.setdefault("step_up_percent", Decimal("0.00"))
    fields.setdefault("template", LeaseTemplate.NNN)
    fields.setdefault("monthly_rent", Decimal("2084.00"))
    fields.setdefault("rent_due_day", 1)
    fields.setdefault("start_date", TODAY.replace(day=1) - dt.timedelta(days=400))
    fields.setdefault("end_date", TODAY + dt.timedelta(days=400))
    return make_lease(**fields)


def schedule_of(lease):
    return [
        (period.effective_from, period.amount, period.origin)
        for period in lease.rent_periods.order_by("effective_from")
    ]


# --- the model's own rules ------------------------------------------------


def test_a_fixed_lease_refuses_step_up_terms():
    lease = make_lease(template=LeaseTemplate.FIXED, step_up_month=9)

    with pytest.raises(ValidationError) as raised:
        lease.full_clean()

    assert "template" in raised.value.message_dict


def test_a_stepped_lease_needs_a_month_and_one_basis():
    lease = make_lease(template=LeaseTemplate.STEP_UP, step_up_percent=Decimal("7.00"))
    with pytest.raises(ValidationError) as raised:
        lease.full_clean()
    assert "step_up_month" in raised.value.message_dict

    both = make_lease(
        template=LeaseTemplate.STEP_UP,
        step_up_month=9,
        step_up_percent=Decimal("7.00"),
        step_up_amount=Decimal("100.00"),
    )
    with pytest.raises(ValidationError) as raised:
        both.full_clean()
    assert "step_up_percent" in raised.value.message_dict

    good = stepped_lease()
    good.full_clean()


def test_a_rent_period_must_fall_on_a_rent_due_date():
    lease = stepped_lease()

    with pytest.raises(ValidationError) as raised:
        make_rent_period(lease, effective_from=dt.date(2027, 1, 7), amount=Decimal("2084.00"))

    assert "effective_from" in raised.value.message_dict


def test_a_rent_period_must_fall_inside_the_term():
    lease = stepped_lease()

    with pytest.raises(ValidationError) as raised:
        make_rent_period(lease, effective_from=dt.date(2026, 12, 5), amount=Decimal("2084.00"))

    assert "effective_from" in raised.value.message_dict


def test_a_fixed_lease_has_no_rent_periods():
    lease = make_lease(template=LeaseTemplate.FIXED, start_date=dt.date(2027, 1, 1), rent_due_day=5)

    with pytest.raises(ValidationError) as raised:
        make_rent_period(lease, effective_from=dt.date(2027, 1, 5))

    assert "lease" in raised.value.message_dict


def test_only_a_triple_net_lease_carries_nnn():
    lease = stepped_lease()

    with pytest.raises(ValidationError) as raised:
        make_nnn_rate(lease, effective_from=dt.date(2027, 1, 5))

    assert "lease" in raised.value.message_dict


def test_an_nnn_rate_may_be_zero_to_suspend_it():
    lease = nnn_lease()

    rate = make_nnn_rate(lease, monthly_amount=Decimal("0.00"))

    assert rate.monthly_amount == Decimal("0.00")


# --- working out the schedule ---------------------------------------------


def test_a_four_year_lease_is_worked_out_in_full():
    """The owner's shape: four years, a rise each September, 7% a year."""
    lease = stepped_lease()

    result = lease_services.generate_rent_schedule(lease)

    assert [date for date, _, _ in schedule_of(lease)] == [
        dt.date(2027, 1, 5),
        dt.date(2027, 9, 5),
        dt.date(2028, 9, 5),
        dt.date(2029, 9, 5),
        dt.date(2030, 9, 5),
    ]
    assert [amount for _, amount, _ in schedule_of(lease)] == [
        Decimal("2084.00"),
        Decimal("2229.88"),
        Decimal("2385.97"),
        Decimal("2552.99"),
        Decimal("2731.70"),
    ]
    assert [origin for _, _, origin in schedule_of(lease)] == [
        RentPeriodOrigin.BASE,
        RentPeriodOrigin.STEP_UP,
        RentPeriodOrigin.STEP_UP,
        RentPeriodOrigin.STEP_UP,
        RentPeriodOrigin.STEP_UP,
    ]
    assert len(result.created) == 5
    assert result.changed


def test_a_fixed_amount_step_adds_that_amount():
    lease = stepped_lease(step_up_percent=None, step_up_amount=Decimal("150.00"))

    lease_services.generate_rent_schedule(lease)

    assert [amount for _, amount, _ in schedule_of(lease)] == [
        Decimal("2084.00"),
        Decimal("2234.00"),
        Decimal("2384.00"),
        Decimal("2534.00"),
        Decimal("2684.00"),
    ]


def test_a_fixed_lease_generates_nothing():
    lease = make_lease(template=LeaseTemplate.FIXED, monthly_rent=Decimal("1850.00"))

    result = lease_services.generate_rent_schedule(lease)

    assert result.created == []
    assert lease.rent_periods.count() == 0
    assert lease.rent_for(TODAY) == Decimal("1850.00")


def test_generating_twice_changes_nothing():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)

    again = lease_services.generate_rent_schedule(lease)

    assert again.created == [] and again.updated == [] and again.removed == []
    assert len(again.kept) == 5
    assert lease.rent_periods.count() == 5


def test_a_step_in_the_start_month_waits_a_year():
    lease = stepped_lease(start_date=dt.date(2027, 9, 1), end_date=dt.date(2029, 8, 31))

    lease_services.generate_rent_schedule(lease)

    assert [date for date, _, _ in schedule_of(lease)] == [
        dt.date(2027, 9, 5),
        dt.date(2028, 9, 5),
    ]


def test_a_step_month_before_the_start_month_waits_for_next_year():
    lease = stepped_lease(
        start_date=dt.date(2027, 3, 1),
        end_date=dt.date(2029, 2, 28),
        step_up_month=1,
    )

    lease_services.generate_rent_schedule(lease)

    assert [date for date, _, _ in schedule_of(lease)] == [
        dt.date(2027, 3, 5),
        dt.date(2028, 1, 5),
        dt.date(2029, 1, 5),
    ]


def test_a_schedule_never_runs_past_the_end_of_the_term():
    lease = stepped_lease(end_date=dt.date(2027, 6, 30))

    lease_services.generate_rent_schedule(lease)

    assert [date for date, _, _ in schedule_of(lease)] == [dt.date(2027, 1, 5)]


def test_the_schedule_follows_a_changed_rule():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    lease.step_up_percent = Decimal("5.00")
    lease.save(update_fields=["step_up_percent"])

    result = lease_services.generate_rent_schedule(lease)

    assert len(result.updated) == 4
    assert lease.rent_for(dt.date(2027, 9, 5)) == Decimal("2188.20")  # 2084 × 1.05


def test_a_period_that_has_been_charged_is_not_rewritten():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    make_charge(
        lease,
        amount=Decimal("2084.00"),
        due_date=dt.date(2027, 1, 5),
        description="Rent for January 2027",
    )
    lease.step_up_percent = Decimal("5.00")
    lease.save(update_fields=["step_up_percent"])

    result = lease_services.generate_rent_schedule(lease)

    assert dt.date(2027, 1, 5) in result.locked
    assert lease.rent_for(dt.date(2027, 1, 5)) == Decimal("2084.00"), "already billed"
    assert lease.rent_for(dt.date(2027, 9, 5)) == Decimal("2188.20"), "not yet billed"


def test_a_hand_set_period_survives_regeneration():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    period = lease.rent_periods.get(effective_from=dt.date(2028, 9, 5))
    lease_services.set_rent_period_amount(period, amount=Decimal("2400.00"), note="renewal")

    lease_services.generate_rent_schedule(lease)

    period.refresh_from_db()
    assert period.amount == Decimal("2400.00")
    assert period.origin == RentPeriodOrigin.MANUAL


def test_a_lease_that_goes_back_to_fixed_loses_its_unlocked_periods():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    lease.template = LeaseTemplate.FIXED
    lease.step_up_month = None
    lease.step_up_percent = None
    lease.save(update_fields=["template", "step_up_month", "step_up_percent"])

    result = lease_services.generate_rent_schedule(lease)

    assert lease.rent_periods.count() == 0
    assert len(result.removed) == 5
    assert lease.rent_for(TODAY) == Decimal("2084.00"), "back to the stored rent"


# --- the NNN amount -------------------------------------------------------


def test_staging_a_rate_applies_from_its_date():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    second = dt.date(first.year + 1, first.month, first.day)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))

    assert lease.nnn_for(first) == Decimal("305.52")
    assert lease.nnn_for(second) == Decimal("305.52")

    lease_services.stage_nnn_rate(lease, effective_from=second, monthly_amount=Decimal("340.00"))

    assert lease.nnn_for(first) == Decimal("305.52"), "this year is untouched"
    assert lease.nnn_for(second) == Decimal("340.00"), "next year is staged"


def test_the_rate_before_the_first_one_is_nothing():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))

    assert lease.nnn_for(first - dt.timedelta(days=1)) == Decimal("0.00")


def test_the_next_nnn_date_is_a_year_on():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))

    assert lease_services.next_nnn_effective_date(lease) == dt.date(
        first.year + 1, first.month, first.day
    )


def test_staging_a_rate_for_a_charged_period_is_refused():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    make_charge(lease, kind=ChargeKind.NNN, amount=Decimal("305.52"), due_date=first)

    with pytest.raises(ValidationError) as raised:
        lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("400.00"))

    assert "effective_from" in raised.value.message_dict


def test_nnn_cannot_be_staged_on_a_step_up_lease():
    lease = stepped_lease()

    with pytest.raises(ValidationError, match="triple-net"):
        lease_services.stage_nnn_rate(
            lease, effective_from=dt.date(2027, 1, 5), monthly_amount=Decimal("100.00")
        )


# --- charging the right amount --------------------------------------------


def test_charges_carry_the_amount_for_each_month():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)

    created = ledger_services.generate_charges(lease, through=dt.date(2027, 12, 31))

    amounts = {
        charge.due_date: charge.amount for charge in created if charge.kind == ChargeKind.RENT
    }
    assert amounts[dt.date(2027, 1, 5)] == Decimal("2084.00")
    assert amounts[dt.date(2027, 8, 5)] == Decimal("2084.00")
    assert amounts[dt.date(2027, 9, 5)] == Decimal("2229.88"), "the step month"
    assert amounts[dt.date(2027, 12, 5)] == Decimal("2229.88")


def test_a_triple_net_month_carries_rent_and_nnn():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))
    lease_services.generate_rent_schedule(lease)

    created = ledger_services.generate_charges(lease, through=first)
    by_kind = {charge.kind: charge for charge in created}

    assert by_kind[ChargeKind.RENT].amount == Decimal("2084.00")
    assert by_kind[ChargeKind.NNN].amount == Decimal("305.52")
    assert by_kind[ChargeKind.NNN].description == f"NNN for {first:%B %Y}"
    assert by_kind[ChargeKind.NNN].get_kind_display() == "NNN"


def test_a_triple_net_lease_with_no_rate_raises_rent_only():
    lease = nnn_lease()

    created = ledger_services.generate_charges(lease, through=TODAY)

    assert created
    assert {charge.kind for charge in created} == {ChargeKind.RENT}


def test_generating_charges_twice_creates_nothing_twice():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))

    created = ledger_services.generate_charges(lease, through=first)
    again = ledger_services.generate_charges(lease, through=first)

    assert len(created) == 2
    assert again == []


def test_a_fixed_lease_never_gets_an_nnn_charge():
    lease = make_lease(
        template=LeaseTemplate.FIXED,
        monthly_rent=Decimal("1850.00"),
        start_date=TODAY.replace(day=1) - dt.timedelta(days=40),
        end_date=TODAY + dt.timedelta(days=200),
        rent_due_day=1,
    )

    created = ledger_services.generate_charges(lease, through=TODAY)

    assert {charge.kind for charge in created} == {ChargeKind.RENT}


# --- what the tenant is told ----------------------------------------------


def test_next_rent_due_is_the_rent_not_the_nnn():
    lease = nnn_lease()
    next_due = lease_services.first_due_on_or_after(lease, TODAY + dt.timedelta(days=1))
    lease_services.stage_nnn_rate(
        lease,
        effective_from=lease_services.first_due_on_or_after(lease, lease.start_date),
        monthly_amount=Decimal("305.52"),
    )
    lease_services.generate_rent_schedule(lease)
    ledger_services.generate_charges(lease, through=next_due)

    ledger = ledger_services.build_ledger(lease)

    assert ledger.next_rent_date == next_due
    assert ledger.next_rent_amount == Decimal("2084.00"), "the rent alone"
    assert ledger.next_due_total == Decimal("2389.52"), "what the month costs"
    assert ledger.next_due_nnn == Decimal("305.52")
    assert ledger.next_due_rent == Decimal("2084.00")
    assert ledger.next_due_billed is True


def test_the_next_due_total_is_forecast_when_nothing_is_raised():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))
    lease_services.generate_rent_schedule(lease)

    ledger = ledger_services.build_ledger(lease)

    assert ledger.next_due_billed is False
    assert ledger.next_due_date == ledger_services.upcoming_rent_date(lease)
    assert ledger.next_due_total == Decimal("2389.52")
    assert ledger.next_due_nnn == Decimal("305.52")


def test_due_now_and_not_yet_due_include_nnn():
    lease = nnn_lease()
    last_month = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    next_month = TODAY.replace(day=1) + dt.timedelta(days=32)
    next_month = next_month.replace(day=1)
    make_charge(lease, amount=Decimal("2084.00"), due_date=last_month)
    make_charge(lease, kind=ChargeKind.NNN, amount=Decimal("305.52"), due_date=last_month)
    make_charge(lease, amount=Decimal("2084.00"), due_date=next_month)
    make_charge(lease, kind=ChargeKind.NNN, amount=Decimal("305.52"), due_date=next_month)

    ledger = ledger_services.build_ledger(lease)

    assert ledger.arrears == Decimal("2389.52")
    assert ledger.due_now == Decimal("2389.52")
    assert ledger.not_yet_due == Decimal("2389.52")


def test_a_stepped_lease_forecasts_the_stepped_rent():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    after_the_step = dt.date(2027, 10, 5)

    assert lease.rent_for(after_the_step) == Decimal("2229.88")
    assert lease.next_rent_change(today=dt.date(2027, 1, 6)).effective_from == dt.date(2027, 9, 5)


# --- the audit trail ------------------------------------------------------


def test_the_schedule_and_the_nnn_are_recorded_with_a_name():
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)

    lease_services.generate_rent_schedule(lease)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("305.52"))
    period = lease.rent_periods.first()
    lease_services.set_rent_period_amount(period, amount=Decimal("2100.00"), note="agreed")

    actions = set(AuditEvent.objects.for_lease(lease).values_list("action", flat=True))
    assert AuditAction.RENT_SCHEDULE_GENERATED in actions
    assert AuditAction.NNN_RATE_SET in actions
    assert AuditAction.RENT_PERIOD_CHANGED in actions


def test_an_unchanged_schedule_records_nothing_new():
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    before = AuditEvent.objects.count()

    lease_services.generate_rent_schedule(lease)

    assert AuditEvent.objects.count() == before


def test_a_schedule_costs_no_extra_queries_once_prefetched(django_assert_num_queries):
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    fresh = type(lease).objects.prefetch_related("rent_periods", "nnn_rates").get(pk=lease.pk)

    with django_assert_num_queries(0):
        for month in range(1, 13):
            fresh.rent_for(dt.date(2027, month, 5))
            fresh.nnn_for(dt.date(2027, month, 5))


# --- the screens and the rules around them --------------------------------


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="lease-manager"))
    return client


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="lease-admin"))
    return client


def a_running_nnn_lease(*, tenants=()):
    """A triple-net tenancy running from last year: rent and NNN both in force."""
    lease = make_lease(
        tenants=list(tenants),
        template=LeaseTemplate.NNN,
        step_up_month=TODAY.month,
        step_up_percent=Decimal("3.00"),
        monthly_rent=Decimal("1000.00"),
        rent_due_day=1,
        start_date=TODAY.replace(day=1) - dt.timedelta(days=400),
        end_date=TODAY + dt.timedelta(days=400),
    )
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    lease_services.stage_nnn_rate(lease, effective_from=first, monthly_amount=Decimal("150.00"))
    lease_services.generate_rent_schedule(lease)
    return lease


def next_due_date():
    following = TODAY.replace(day=1) + dt.timedelta(days=32)
    return following.replace(day=1)


def test_activating_works_out_the_term_and_raises_the_first_charges(signed_in):
    tenant = make_tenant(username="ada")
    start = TODAY.replace(day=1)
    lease = make_lease(
        tenants=[tenant],
        status=LeaseStatus.DRAFT,
        template=LeaseTemplate.STEP_UP,
        step_up_month=start.month,
        step_up_percent=Decimal("5.00"),
        monthly_rent=Decimal("1000.00"),
        rent_due_day=1,
        start_date=start,
        end_date=start + dt.timedelta(days=400),
    )

    response = signed_in.post(reverse("leases:lease-activate", args=[lease.pk]))

    assert response.status_code == 302
    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ACTIVE
    assert lease.rent_periods.count() == 2, "this year and next"
    assert lease.rent_for(start + dt.timedelta(days=400)) == Decimal("1050.00")
    assert lease.charges.rent().exists(), "the first months are billed at activation"
    assert AuditEvent.objects.filter(action=AuditAction.LEASE_ACTIVATED, lease=lease).exists()


def test_a_manager_reads_the_schedule_but_cannot_change_it(signed_in):
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    period = lease.rent_periods.order_by("effective_from").first()

    body = strip_tags(
        signed_in.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()
    )
    assert "Rent" in body and "2,084.00" in body
    assert "Work the schedule out again" not in body, "regenerating is an admin's act"
    assert "Set by hand" not in body

    assert (
        signed_in.post(reverse("leases:rent-schedule-generate", args=[lease.pk])).status_code == 403
    )
    assert (
        signed_in.get(reverse("leases:rent-period-update", args=[lease.pk, period.pk])).status_code
        == 403
    )
    assert signed_in.get(reverse("leases:nnn-stage", args=[lease.pk])).status_code == 403


def test_an_admin_can_regenerate_and_stage_nnn(as_admin):
    lease = make_lease(
        template=LeaseTemplate.NNN,
        step_up_month=TODAY.month,
        step_up_percent=Decimal("3.00"),
        monthly_rent=Decimal("1000.00"),
        rent_due_day=1,
        start_date=TODAY.replace(day=1) - dt.timedelta(days=400),
        end_date=TODAY + dt.timedelta(days=400),
    )
    first = lease_services.first_due_on_or_after(lease, lease.start_date)

    response = as_admin.post(reverse("leases:rent-schedule-generate", args=[lease.pk]))

    assert response.status_code == 302
    assert lease.rent_periods.exists()

    response = as_admin.post(
        reverse("leases:nnn-stage", args=[lease.pk]),
        {
            "effective_from": first.isoformat(),
            "monthly_amount": "305.52",
            "note": "November calculation",
        },
    )

    assert response.status_code == 302
    assert lease.nnn_for(first) == Decimal("305.52")


def test_a_period_can_be_set_by_hand_until_it_has_been_charged(as_admin):
    lease = stepped_lease()
    lease_services.generate_rent_schedule(lease)
    period = lease.rent_periods.order_by("effective_from").first()
    url = reverse("leases:rent-period-update", args=[lease.pk, period.pk])

    response = as_admin.post(url, {"amount": "2100.00", "note": "agreed at renewal"})

    assert response.status_code == 302
    period.refresh_from_db()
    assert period.amount == Decimal("2100.00")
    assert period.origin == RentPeriodOrigin.MANUAL

    make_charge(lease, amount=Decimal("2100.00"), due_date=period.effective_from)
    response = as_admin.post(url, {"amount": "2200.00", "note": "again"})

    assert response.status_code == 200, "the refusal is shown, not swallowed"
    period.refresh_from_db()
    assert period.amount == Decimal("2100.00")
    assert "adjustment" in strip_tags(response.content.decode())


def test_the_period_screen_never_reaches_another_lease(as_admin):
    mine = stepped_lease()
    theirs = stepped_lease(unit=make_unit(identifier="Elsewhere"))
    lease_services.generate_rent_schedule(mine)
    lease_services.generate_rent_schedule(theirs)
    their_period = theirs.rent_periods.order_by("effective_from").first()

    response = as_admin.get(reverse("leases:rent-period-update", args=[mine.pk, their_period.pk]))

    assert response.status_code == 404


def test_an_ended_lease_refuses_schedule_changes(as_admin):
    lease = stepped_lease(
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    period = make_rent_period(lease, amount=Decimal("2084.00"))

    response = as_admin.post(reverse("leases:rent-schedule-generate", args=[lease.pk]), follow=True)
    assert "has ended" in strip_tags(response.content.decode())

    assert (
        as_admin.get(reverse("leases:rent-period-update", args=[lease.pk, period.pk])).status_code
        == 302
    )
    assert as_admin.get(reverse("leases:nnn-stage", args=[lease.pk])).status_code == 302


def test_the_lease_page_shows_the_schedule_and_the_staged_nnn(as_admin):
    lease = a_running_nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)

    body = strip_tags(
        as_admin.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()
    )

    assert "Triple net (NNN)" in body
    assert "In force now: $150.00 a month from" in " ".join(body.split())
    assert "Stage the next NNN" in body
    assert date_format(first) in body


def test_the_tenant_lease_page_shows_how_the_rent_is_worked_out(client):
    tenant = make_tenant(username="ada")
    lease = a_running_nnn_lease(tenants=[tenant])
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("tenancy:lease")).content.decode()).split())

    assert "How your rent is worked out" in body
    assert "Base rent" in body
    assert f"${lease.current_base_rent:,.2f}" in body
    assert "NNN" in body and "$150.00" in body
    assert f"A month, at today's figures ${lease.current_month_total:,.2f}" in body


def test_the_tenant_summary_names_the_nnn_part(client):
    tenant = make_tenant(username="ada")
    lease = a_running_nnn_lease(tenants=[tenant])
    due = next_due_date()
    make_charge(lease, amount=Decimal("1000.00"), due_date=due)
    make_charge(lease, kind=ChargeKind.NNN, amount=Decimal("150.00"), due_date=due)
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("payments:home")).content.decode()).split())

    assert f"Next rent due {date_format(due)}: $1,150.00." in body
    assert "Rent $1,000.00 plus NNN $150.00." in body


def test_the_desk_sees_the_month_total_in_the_overview(as_admin):
    lease = a_running_nnn_lease()
    due = next_due_date()
    make_charge(lease, amount=Decimal("1000.00"), due_date=due)
    make_charge(lease, kind=ChargeKind.NNN, amount=Decimal("150.00"), due_date=due)

    body = " ".join(strip_tags(as_admin.get(reverse("ledger:overview")).content.decode()).split())

    assert f"{date_format(due)} · $1,150.00" in body


def test_the_ledger_page_offers_to_create_rent_and_nnn(as_admin):
    lease = a_running_nnn_lease()
    next_due = next_due_date()

    response = as_admin.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    body = " ".join(strip_tags(response.content.decode()).split())
    assert "rent charge" in body and "NNN charge" in body
    assert lease.charges.filter(kind=ChargeKind.NNN, due_date=next_due).exists()


def test_nnn_can_be_staged_after_the_rent_has_been_charged():
    """The ordinary case: November's NNN is staged while the rent is already billed."""
    lease = nnn_lease()
    first = lease_services.first_due_on_or_after(lease, lease.start_date)
    make_charge(lease, amount=Decimal("1000.00"), due_date=first)

    rate = lease_services.stage_nnn_rate(
        lease, effective_from=first, monthly_amount=Decimal("150.00")
    )

    assert rate.monthly_amount == Decimal("150.00")
    assert lease.nnn_for(first) == Decimal("150.00")
