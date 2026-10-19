"""Charts never change authoritative cents or disguise invalid allocations."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.responsibilities.presentation import allocation_chart, unit_color
from apps.responsibilities.services import allocate_monthly


def chart_for(amounts, *, remainder="rhp", cap="79.00", vacant=()):
    units = [SimpleNamespace(pk=i + 1, identifier=f"Unit {i + 1}") for i in range(len(amounts))]
    worksheet = allocate_monthly(
        SimpleNamespace(monthly_total=Decimal(cap)),
        units=units,
        amounts={u.pk: Decimal(a) for u, a in zip(units, amounts, strict=True)},
        percentages={},
        bases={u.pk: "amount" for u in units},
        remainder=remainder,
    )
    rows = [
        {"unit": r.unit, "amount": r.amount, "percent": r.percent, "vacant": r.unit.pk in vacant}
        for r in worksheet.rows
    ]
    return worksheet, allocation_chart(worksheet, rows)


def test_exact_79_55_24_split_uses_calculator_cents():
    worksheet, chart = chart_for(["55.00", "45.80"], remainder="2")
    assert [r.amount for r in worksheet.rows] == [Decimal("55.00"), Decimal("24.00")]
    assert [s["percent"] for s in chart["segments"]] == [Decimal("69.62"), Decimal("30.38")]
    assert sum(Decimal(s["length"]) for s in chart["segments"]) == Decimal("100.000000")


def test_vacant_allocation_is_not_counted_twice():
    _, chart = chart_for(["30.00", "20.00"], vacant=(2,))
    assert len(chart["segments"]) == 3
    assert chart["segments"][1]["vacant"] is True
    assert chart["segments"][2]["amount"] == Decimal("29.00")
    assert sum(s["amount"] for s in chart["segments"]) == Decimal("79.00")


@pytest.mark.parametrize(
    ("amounts", "cap", "state"),
    [
        (["80.00", "10.00"], "79.00", "over"),
        (["0.00"], "0.00", "zero"),
    ],
)
def test_invalid_or_zero_allocation_has_no_misleading_ring(amounts, cap, state):
    _, chart = chart_for(amounts, cap=cap)
    assert chart == {"state": state, "segments": []}


def test_colors_follow_identity_not_order():
    assert unit_color(2) == unit_color(2)
    assert unit_color(1) != unit_color(2)
