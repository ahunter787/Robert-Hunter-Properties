"""Small shared helpers that do not belong to one domain."""

import calendar
import datetime as dt


def ordinal(number: int) -> str:
    """Render a day of the month as an ordinal: 1 → "1st", 22 → "22nd"."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def due_date_in(year: int, month: int, day: int) -> dt.date:
    """The due date in one month, clamped to a day that exists.

    A lease with a rent due day of the 31st is due on the 28th in February (29th
    in a leap year) and the 30th in April: the agreement says "the last day",
    which is what the 31st means in a short month. Phase 4 is where that rule
    lives, as promised in the phase guide.
    """
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last_day))


def due_date_on_or_after(day: dt.date, rent_due_day: int) -> dt.date:
    """The first rent due date on or after ``day``, for a lease due on that day.

    One definition of "when does this tenancy next fall due", used by the lease's
    own screens and by a property responsibility working out which months its bill
    covers (E1, E2).
    """
    year, month = day.year, day.month
    due = due_date_in(year, month, rent_due_day)
    while due < day:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        due = due_date_in(year, month, rent_due_day)
    return due


def month_after(day: dt.date, months: int = 1) -> tuple[int, int]:
    """The ``(year, month)`` a few months after ``day``'s month."""
    year, month = day.year, day.month
    for _ in range(months):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return year, month
