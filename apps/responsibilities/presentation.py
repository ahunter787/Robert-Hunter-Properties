"""Allocation chart geometry only; the calculator remains authoritative."""

from decimal import Decimal

UNIT_COLORS = ("#2766b2", "#b8437d", "#7252ae", "#237c76", "#a35c21", "#526a88")


def unit_color(unit_id):
    return UNIT_COLORS[(unit_id - 1) % len(UNIT_COLORS)]


def allocation_chart(worksheet, rows):
    if worksheet is None:
        return {"state": "invalid", "segments": []}
    total = worksheet.assigned + worksheet.left
    if worksheet.over:
        return {"state": "over", "segments": []}
    if total <= 0:
        return {"state": "zero", "segments": []}
    segments = []
    offset = Decimal("0")
    for row in rows:
        length = row["amount"] / total * Decimal("100")
        if length > 0:
            segments.append(
                {
                    "unit_id": row["unit"].pk,
                    "label": row["unit"].identifier,
                    "amount": row["amount"],
                    "percent": row["percent"],
                    "vacant": row["vacant"],
                    "color": unit_color(row["unit"].pk),
                    "length": format(length, ".6f"),
                    "offset": format(-offset, ".6f"),
                }
            )
            offset += length
    if worksheet.left > 0:
        segments.append(
            {
                "label": "Unallocated — RHP",
                "amount": worksheet.left,
                "percent": worksheet.left / total * Decimal("100"),
                "color": "#707b76",
                "length": format(Decimal("100") - offset, ".6f"),
                "offset": format(-offset, ".6f"),
            }
        )
    return {"state": "ready", "segments": segments, "total": total}
