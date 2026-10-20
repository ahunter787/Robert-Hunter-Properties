"""Template filters for RHP presentation."""

from decimal import Decimal, InvalidOperation

from django import template

from apps.common.dates import ordinal

register = template.Library()


@register.filter
def financial_charge_icon(kind):
    from apps.ledger.presentation import charge_icon

    return charge_icon(kind)


@register.filter
def financial_charge_label(charge):
    from apps.ledger.presentation import charge_label

    return charge_label(charge)


@register.inclusion_tag("components/financial_summary.html")
def financial_summary(ledger):
    return financial_summary_data(ledger)


@register.simple_tag
def financial_summary_data(ledger):
    from apps.ledger.presentation import financial_summary as project

    return project(ledger)


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
def absolute(value):
    """The size of an amount, ignoring its direction.

    A ledger shows the sign itself (``+`` for a charge, ``−`` for a payment) and
    then the amount, never a minus sign inside the currency.
    """
    try:
        return abs(Decimal(value))
    except InvalidOperation, TypeError, ValueError:
        return value


@register.filter
def ordinal_day(value) -> str:
    """1 → ``1st``. Named to stay distinct from humanize's numeric filter."""
    try:
        return ordinal(int(value))
    except TypeError, ValueError:
        return ""
