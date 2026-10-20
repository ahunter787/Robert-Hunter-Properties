"""Generate five synthetic documentation examples; never imported by the application."""

import json
import re
import runpy
import textwrap
from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
COLORS = {
    "received": "#1c6b45",
    "charge": "#9c231c",
    "cost": "#9c231c",
    "pending": "#171717",
    "credit": "#1c6b45",
    "change": "#6b21a8",
    "history": "#171717",
}


def text(x, y, value, *, size=11, bold=False, color="#202326"):
    return {
        "type": "text",
        "x": x,
        "y": y,
        "text": value,
        "size": size,
        "bold": bold,
        "fill": color,
    }


def rect(x, y, w, h, *, fill="#ffffff", stroke="#bbbbbb"):
    return {"type": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "stroke": stroke}


def amount_text(x, y, value, kind, *, size=11, bold=False):
    """Color amounts, never names, percentages or ordinary bookkeeping text."""
    elements = []
    font = "Helvetica-Bold" if bold else "Helvetica"
    previous = ""
    for part in re.split(r"(\$[\d,]+\.\d{2})", value):
        amount_color = COLORS[kind]
        if re.search(r"(?:reduced|earlier)\s*$", previous):
            amount_color = COLORS["change"]
        elif re.search(r"\bto\s*$", previous):
            amount_color = COLORS["charge"]
        elements.append(
            text(
                x,
                y,
                part,
                size=size,
                bold=bold,
                color=amount_color if part.startswith("$") else "#171717",
            )
        )
        x += stringWidth(part, font, size)
        previous = part
    return elements


def page(title, heading, lines, phone, note):
    elements = [
        text(30, 94, "Desktop structure", bold=True),
        text(546, 94, "Phone structure", bold=True),
        rect(30, 108, 486, 362),
        rect(546, 108, 216, 400),
        text(46, 135, "Alder Court / Studio A / Alex Example", size=10),
        text(558, 135, "Studio A", size=13, bold=True),
    ]
    elements.extend(amount_text(46, 163, heading, "cost", size=16, bold=True))
    y = 195
    for label, value, kind in lines:
        elements.extend(amount_text(46, y, label, kind, bold=True))
        detail_kind = "cost" if value.startswith("Studio B:") else "history"
        if "past due" in value:
            detail_kind = "charge"
        elements.extend(amount_text(46, y + 19, value, detail_kind, size=10))
        y += 58
    y = 169
    for value in phone:
        kind = "history"
        if any(
            word in value
            for word in ("Due now", "Past due", "Current:", "Result:", "Studio A:", "Studio B:")
        ):
            kind = "charge"
        elif "Reduce by" in value:
            kind = "change"
        elif "Amount:" in value:
            kind = "received"
        elements.extend(amount_text(558, y, value, kind, size=10))
        y += 26
    elements.extend(
        [
            text(
                30,
                570,
                "Labels and patterns carry meaning in grayscale; "
                "production colors remain full-color.",
                size=10,
            ),
        ]
    )
    for index, line in enumerate(textwrap.wrap(note, width=112)):
        elements.append(text(30, 530 + index * 15, line, size=10, bold=True))
    return {
        "title": title,
        "subtitle": "Approved amount colors | Proposed task flows | Synthetic figures",
        "width": 792,
        "height": 612,
        "elements": elements,
    }


def main():
    book = {
        "title": "RHP financial clarity - five task examples",
        "pages": [
            page(
                "1. One lease financial view",
                "Rent & Payments",
                [
                    (
                        "Amount owed now: $100.00",
                        "Includes $20.00 past due. Recorded charges only.",
                        "charge",
                    ),
                    (
                        "Payment received: $500.00",
                        "Recorded check payment; not a portal transfer.",
                        "received",
                    ),
                    (
                        "Next scheduled rent: $1,850.00",
                        "Due Nov 1, 2026. Not yet added to the account.",
                        "history",
                    ),
                    (
                        "Corrected charges: $600.00",
                        "Includes a $120.00 charge reduced $20.00 to $100.00.",
                        "charge",
                    ),
                ],
                [
                    "Rent & Payments",
                    "Due now: $100.00",
                    "Past due: $20.00",
                    "Next rent: $1,850.00",
                    "Not added to account",
                    "Record payment",
                    "Add one-time charge",
                    "Transactions",
                    "Inline corrections",
                    "History (expand)",
                ],
                "Both preserved lease/ledger URLs lead to the same financial reading surface.",
            ),
            page(
                "2. Set up starting account records",
                "Choose one setup method",
                [
                    (
                        "1. Choose: Full history / Starting balance",
                        "Do not display both methods' inputs together.",
                        "history",
                    ),
                    (
                        "2. Starting balance: $200.00 owed",
                        "Balance as of Oct 1; charges begin Oct 1. Source: old records.",
                        "charge",
                    ),
                    (
                        "3. Review the resulting account",
                        "One starting charge; no newly received payment.",
                        "history",
                    ),
                    (
                        "Confirm starting records",
                        "No calculation of implied prior receipts in this proposal.",
                        "history",
                    ),
                ],
                [
                    "Starting records",
                    "Step 1 of 3",
                    "Choose a method",
                    "Full history",
                    "Starting balance",
                    "Continue",
                    "Back / Cancel",
                    "Only relevant fields",
                    "appear in step 2.",
                ],
                "Historical setup is not new cash; "
                "the separate receipt calculator stays out of scope.",
            ),
            page(
                "3. Record a payment",
                "Record payment received",
                [
                    ("Amount: $500.00", "Received on Oct 20, 2026. Method: Check.", "received"),
                    (
                        "Reference (optional)",
                        "Check number or source reference; no bank credentials.",
                        "history",
                    ),
                    (
                        "Or record an expected payment",
                        "Expected on date; no received label or balance reduction.",
                        "pending",
                    ),
                    (
                        "Record $500.00 payment",
                        "Records an outside payment. Does not move money.",
                        "received",
                    ),
                ],
                [
                    "Record payment",
                    "Amount: $500.00",
                    "Received on",
                    "Oct 20, 2026",
                    "Method: Check",
                    "Reference (optional)",
                    "Record payment",
                    "Cancel",
                    "Expected instead?",
                    "Separate state label",
                ],
                "Received amounts green; expected payments black. "
                "Neither is bank-reconciled proof.",
            ),
            page(
                "4. Correct a charge",
                "Reduce this charge",
                [
                    (
                        "Current charge: $100.00",
                        "Original $120.00 less earlier $20.00 correction.",
                        "charge",
                    ),
                    (
                        "Reduce by: $10.00",
                        "Change amount, not replacement total. Reason required.",
                        "change",
                    ),
                    (
                        "After this correction: $90.00",
                        "No refund or cash transfer. Original entries remain.",
                        "charge",
                    ),
                    (
                        "Review, then confirm reduction",
                        "Quick-fill only changes input; never silently submits.",
                        "history",
                    ),
                ],
                [
                    "Correct charge",
                    "Current: $100.00",
                    "Reduce / Increase",
                    "Reduce by $10.00",
                    "Result: $90.00",
                    "Reason",
                    "Review change",
                    "Confirm reduction",
                    "Back / Cancel",
                    "Original stays visible",
                ],
                "Keep corrections inline under their original charge; "
                "do not replace stored history.",
            ),
            page(
                "5. Allocate a property bill",
                "Electricity: $237.00 / 3 months",
                [
                    (
                        "Monthly amount to allocate: $79.00",
                        "Compact ring + matching text; preserve unit colors.",
                        "history",
                    ),
                    (
                        "Studio A: $55.00 / 69.62%",
                        "Studio B: $24.00 / 30.38%, calculated remainder.",
                        "cost",
                    ),
                    (
                        "Assign remaining monthly amount to Studio B",
                        "Allocation only. A vacant unit stays funded by RHP.",
                        "history",
                    ),
                    (
                        "Review and save allocations",
                        "No tenant charges added. Bill payment is not recorded.",
                        "history",
                    ),
                ],
                [
                    "Electricity allocation",
                    "$79.00 per month",
                    "Small ring + legend",
                    "Remainder: Studio B",
                    "Studio A: $55.00",
                    "Studio B: $24.00",
                    "Calculated remainder",
                    "Review allocation",
                    "Save allocations",
                    "No tenant charges yet",
                ],
                "Cost receipt icon, not paid-out arrow; do not recolor unit slices by status.",
            ),
        ],
    }
    source = BASE / "sources" / "financial-examples.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(book, indent=2) + "\n")
    renderer = runpy.run_path(str(ROOT / ".agents/skills/rhp-design-diagrams/scripts/render.py"))
    for gray in (False, True):
        renderer["render"](book, BASE / "artifacts/financial-examples", grayscale=gray)


if __name__ == "__main__":
    main()
