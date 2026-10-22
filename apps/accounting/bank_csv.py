"""Minimal bank statement CSV parsing (B3: CSV/OFX first, no aggregator dependency)."""

import csv
import datetime as dt
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

DATE_ALIASES = ("date", "transaction date", "posted date")
DESCRIPTION_ALIASES = ("description", "memo", "details", "payee")
AMOUNT_ALIASES = ("amount", "transaction amount")
REFERENCE_ALIASES = ("reference", "check number", "ref")


def _column(headers, aliases, required, label):
    lowered = {header.strip().lower(): header for header in headers}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    if required:
        raise ValidationError(f"The statement has no {label} column.")
    return None


def _date(value):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Could not read the statement date {value!r}.")


def parse(text: str) -> list[dict]:
    """Return rows with date, description, amount and optional reference."""
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValidationError("The file is empty or is not a CSV with a header row.")
    date_column = _column(reader.fieldnames, DATE_ALIASES, True, "date")
    description_column = _column(reader.fieldnames, DESCRIPTION_ALIASES, True, "description")
    amount_column = _column(reader.fieldnames, AMOUNT_ALIASES, True, "amount")
    reference_column = _column(reader.fieldnames, REFERENCE_ALIASES, False, "reference")
    rows = []
    for number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values()):
            continue
        try:
            raw_amount = (raw.get(amount_column) or "").strip().replace(",", "").replace("$", "")
            amount = Decimal(raw_amount)
        except (InvalidOperation, AttributeError) as exc:
            raise ValidationError(f"Row {number}: the amount is not a number.") from exc
        rows.append(
            {
                "date": _date(raw.get(date_column)),
                "description": (raw.get(description_column) or "").strip(),
                "amount": amount,
                "reference": (raw.get(reference_column) or "").strip() if reference_column else "",
            }
        )
    if not rows:
        raise ValidationError("The statement has no transaction rows.")
    return rows
