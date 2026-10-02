"""The coming due question: when the next rent falls due, and for how much.

Separate from arrears on purpose. "Next rent due" is the *incoming* month, not the
oldest unpaid one, and it answers even when the office has not raised the charge
yet — the lease says when rent falls due, so nobody has to press a button for a
tenant to see the date (ADR-012).

The boundary table passes ``today`` explicitly, so it says the same thing on any
day it is run; the ledger-level tests below work from today's date.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.leases.models import LeaseStatus
from apps.ledger import services
from tests.factories import make_charge, make_lease, make_payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
LONG_TERM = (TODAY - dt.timedelta(days=365), TODAY + dt.timedelta(days=730))


def a_lease(**fields):
    start, end = LONG_TERM
    fields.setdefault("start_date", start)
    fields.setdefault("end_date", end)
    return make_lease(**fields)


def month_before(day: dt.date, months: int) -> tuple[int, int]:
    """The (year, month) a few months before ``day``'s month."""
    year, month = day.year, day.month
    for _ in range(months):
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return year, month


def month_after(day: dt.date, months: int) -> tuple[int, int]:
    year, month = day.year, day.month
    for _ in range(months):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return year, month


# --- the boundary table: what the next due date is -------------------------


def test_the_due_date_this_month_answers_when_it_is_still_ahead():
    lease = a_lease(rent_due_day=20)

    assert services.upcoming_rent_date(lease, today=dt.date(2026, 4, 2)) == dt.date(2026, 4, 20)


def test_a_due_date_that_has_passed_rolls_to_the_next_month():
    lease = a_lease(rent_due_day=5)

    assert services.upcoming_rent_date(lease, today=dt.date(2026, 4, 9)) == dt.date(2026, 5, 5)


def test_a_due_date_falling_today_means_the_next_one_is_a_month_away():
    """Rent due today is due now, not the next rent."""
    lease = a_lease(rent_due_day=9)

    assert services.upcoming_rent_date(lease, today=dt.date(2026, 4, 9)) == dt.date(2026, 5, 9)


def test_a_day_the_month_does_not_have_is_clamped():
    lease = a_lease(rent_due_day=31)

    assert services.upcoming_rent_date(lease, today=dt.date(2026, 1, 5)) == dt.date(2026, 1, 31)
    assert services.upcoming_rent_date(lease, today=dt.date(2026, 1, 31)) == dt.date(2026, 2, 28)


def test_a_lease_ending_before_the_next_due_date_has_no_next_rent():
    lease = a_lease(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 4, 3),
        rent_due_day=5,
    )

    assert services.upcoming_rent_date(lease, today=dt.date(2026, 4, 2)) is None


def test_an_ended_lease_never_falls_due_again():
    lease = a_lease(
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )

    assert services.upcoming_rent_date(lease) is None


def test_a_draft_lease_is_not_charged():
    """A draft's terms can still change, so it forecasts nothing."""
    lease = a_lease(status=LeaseStatus.DRAFT)

    assert services.upcoming_rent_date(lease) is None


def test_a_tenancy_that_has_not_started_is_due_its_first_month():
    lease = a_lease(
        start_date=dt.date(2026, 5, 20),
        end_date=dt.date(2027, 5, 19),
        rent_due_day=5,
    )

    # May's 5th is before the term begins; the first rent is June's.
    assert services.upcoming_rent_date(lease, today=dt.date(2026, 4, 2)) == dt.date(2026, 6, 5)


# --- the ledger's answer, on the day the test runs -------------------------


def test_the_coming_month_is_forecast_before_it_is_billed():
    """The owner's case: months charged, the incoming one not raised yet."""
    lease = a_lease(rent_due_day=1, monthly_rent=Decimal("2084.00"))
    for months_back in range(1, 4):
        year, month = month_before(TODAY, months_back)
        make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))

    ledger = services.build_ledger(lease)
    year, month = month_after(TODAY, 1)

    assert ledger.next_charge is None, "nothing after today has been raised"
    assert ledger.next_rent_date == dt.date(year, month, 1)
    assert ledger.next_rent_amount == Decimal("2084.00")


def test_a_raised_charge_for_the_coming_month_is_the_next_rent():
    lease = a_lease(rent_due_day=1, monthly_rent=Decimal("2084.00"))
    year, month = month_after(TODAY, 1)
    charge = make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))

    ledger = services.build_ledger(lease)
    assert ledger.next_charge.date == charge.due_date
    assert ledger.next_charge.title == charge.description
    assert ledger.next_rent_date == charge.due_date
    assert ledger.next_rent_amount == Decimal("2084.00")


def test_the_next_rent_is_what_is_left_on_the_coming_charge():
    lease = a_lease(rent_due_day=1, monthly_rent=Decimal("2084.00"))
    year, month = month_after(TODAY, 1)
    make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    ledger = services.build_ledger(lease)
    assert ledger.next_rent_amount == Decimal("1084.00"), "what is left, not the gross"


def test_the_oldest_money_settles_the_oldest_month_first():
    """So an incoming month is untouched while arrears remain."""
    lease = a_lease(rent_due_day=1, monthly_rent=Decimal("2084.00"))
    for months_back in range(1, 3):
        year, month = month_before(TODAY, months_back)
        make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))
    year, month = month_after(TODAY, 1)
    make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    ledger = services.build_ledger(lease)
    assert ledger.arrears == Decimal("3168.00"), "two months billed less the payment"
    assert ledger.next_rent_amount == Decimal("2084.00")
    assert ledger.not_yet_due == Decimal("2084.00")


def test_an_ended_lease_has_an_empty_next_rent_card():
    lease = a_lease(
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=30),
    )
    make_charge(lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=60))

    ledger = services.build_ledger(lease)
    assert ledger.next_rent_date is None
    assert ledger.next_rent_amount == Decimal("0.00")
    assert ledger.due_now == Decimal("100.00"), "an ended lease can still owe"


def test_the_next_rent_is_not_the_oldest_unpaid_month():
    """The owner's numbers, read as a date: late money is not the next rent."""
    lease = a_lease(rent_due_day=5, monthly_rent=Decimal("2084.00"))
    for month in (7, 8, 9):
        make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(2026, month, 5))

    next_date = services.upcoming_rent_date(lease, today=dt.date(2026, 10, 2))
    assert next_date == dt.date(2026, 10, 5), "the incoming month, not July"
    assert lease.rent_for(next_date) == Decimal("2084.00")


def test_paying_every_billed_month_leaves_nothing_late():
    """Four months billed and paid: what is late is not what is coming."""
    lease = a_lease(rent_due_day=1, monthly_rent=Decimal("2084.00"))
    for months_back in range(1, 3):
        year, month = month_before(TODAY, months_back)
        make_charge(lease, amount=Decimal("2084.00"), due_date=dt.date(year, month, 1))
    make_payment(lease, amount=Decimal("4168.00"), payment_date=TODAY)

    ledger = services.build_ledger(lease)
    year, month = month_after(TODAY, 1)

    assert ledger.arrears == Decimal("0.00"), "two months billed, two months paid"
    assert ledger.due_now == Decimal("0.00")
    assert ledger.next_charge is None
    assert ledger.next_rent_date == dt.date(year, month, 1)
    assert ledger.next_rent_amount == Decimal("2084.00")
