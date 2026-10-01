"""Template filters for RHP presentation."""

from decimal import Decimal, InvalidOperation

from django import template

from apps.common.dates import ordinal

register = template.Library()


@register.filter
def money(value) -> str:
    """Render an amount as US dollars: ``1850`` → ``$1,850.00``."""
    if value in (None, ""):
        return "—"
    try:
        amount = Decimal(value)
    except InvalidOperation, TypeError, ValueError:
        return "—"
    return f"${amount:,.2f}"


@register.filter
def ordinal_day(value) -> str:
    """1 → ``1st``. Named to stay distinct from humanize's numeric filter."""
    try:
        return ordinal(int(value))
    except TypeError, ValueError:
        return ""
