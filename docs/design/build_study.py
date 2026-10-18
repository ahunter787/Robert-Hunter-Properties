"""Build the synthetic RHP wireframe study using the project diagram skill."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "rhp_diagrams", ROOT / ".agents/skills/rhp-design-diagrams/scripts/render.py"
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

INK = "#202326"
YELLOW = "#fff3cd"
GREEN = "#236744"
RED = "#9c231c"


def text(e, x, y, value, size=11, *, bold=False, fill=INK):
    e.append(
        {"type": "text", "x": x, "y": y, "text": value, "size": size, "bold": bold, "fill": fill}
    )


def rect(e, x, y, w, h, fill="#ffffff", stroke="#c4c4c4"):
    e.append({"type": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "stroke": stroke})


def line(e, x, y, x2, y2, *, dash=False):
    e.append({"type": "line", "x": x, "y": y, "x2": x2, "y2": y2, "dash": dash})


def button(e, x, y, label, w=140):
    rect(e, x, y, w, 27, "#f4f4f4", "#555555")
    text(e, x + 9, y + 18, label, 10, bold=True)


def note(e, x, y, label, detail, w):
    rect(e, x, y, w, 53, YELLOW)
    text(e, x + 10, y + 20, label, 11, bold=True)
    text(e, x + 10, y + 39, detail, 9)


def shell(e, theme, screen, phone):
    domain = "Rent & Payments" if screen == "ledger" else "Maintenance"
    if phone:
        x, y, w = 158, 91, 296
        rect(e, x - 10, y - 10, w + 20, 638, stroke="#555555")
        text(e, x, y + 14, "RHP", 14, bold=True)
        text(e, x + 194, y + 14, "Menu   Account", 10)
        line(e, x, y + 26, x + w, y + 26)
        labels = {
            "portfolio-workspace": f"Portfolio / {domain}",
            "operations-desk": f"Work / {domain}",
            "calm-portal": f"Manage / {domain}",
        }
        text(e, x, y + 46, "Home / Maintenance" if screen == "tenant" else labels[theme], 9)
        return x, y + 76, w
    rect(e, 30, 90, 732, 460)
    text(e, 44, 113, "RHP", 14, bold=True)
    text(e, 666, 113, "Account", 10)
    line(e, 30, 128, 762, 128)
    if screen == "tenant":
        text(e, 48, 151, "Home     Lease     Payments     Documents     Maintenance", 11)
        line(e, 48, 164, 744, 164)
        return 68, 191, 656
    if theme == "portfolio-workspace":
        line(e, 175, 128, 175, 550)
        for i, label in enumerate(
            [
                "Overview",
                "Properties",
                "Leases",
                "Rent & Payments",
                "Maintenance",
                "Documents",
                "Tenants",
            ]
        ):
            text(e, 44, 159 + i * 33, label, 10, bold=label == domain)
        text(e, 196, 151, f"{domain} / Maple Court", 10)
        return 196, 183, 544
    if theme == "operations-desk":
        text(e, 48, 151, "Overview     Portfolio     Rent & Payments     Work     Documents", 11)
        line(e, 48, 164, 744, 164)
        if screen in ("queue", "detail"):
            line(e, 219, 164, 219, 550)
            text(e, 44, 191, "Work queue", 12, bold=True)
            text(e, 44, 217, "3 active / 1 follow-up", 9)
            for i, label in enumerate(["Kitchen leak", "Entry light", "Roof inspection"]):
                rect(e, 40, 234 + i * 69, 168, 58, YELLOW if i == 0 else "#ffffff")
                text(e, 49, 253 + i * 69, label, 10, bold=True)
                text(e, 49, 273 + i * 69, "Maple Court / Unit A", 9)
            return 239, 193, 501
        return 54, 193, 682
    text(
        e, 48, 151, "Overview       Portfolio       Work       Rent & Payments       Documents", 11
    )
    line(e, 48, 166, 744, 166)
    text(
        e,
        64,
        189,
        "Lease account     Transactions     History"
        if screen == "ledger"
        else "Maintenance     Requests     Vendors",
        10,
    )
    return 64, 222, 664


def queue(e, x, y, w, phone):
    text(e, x, y, "Maintenance", 18, bold=True)
    text(e, x, y + 23, "3 active requests / 1 needs follow-up", 10)
    button(e, x, y + 38, "Create request")
    if phone:
        text(e, x, y + 91, "Filters: Property / Status / More", 10)
        for i, (label, status) in enumerate(
            [
                ("Kitchen leak", "High / Waiting / 2 days"),
                ("Entry light", "Normal / Open / 1 day"),
                ("Roof inspection", "Normal / Scheduled / 3 days"),
            ]
        ):
            yy = y + 109 + i * 100
            rect(e, x, yy, w, 84, YELLOW if i == 0 else "#ffffff")
            text(e, x + 12, yy + 22, label, 12, bold=True)
            text(e, x + 12, yy + 44, "Maple Court / Unit A", 10)
            text(e, x + 12, yy + 65, status, 10)
        text(e, x, y + 437, "Sorted by urgency, then age", 10)
    else:
        text(e, x, y + 91, "Property: All    Status: Active    Assignment: All    More filters", 9)
        text(e, x, y + 117, "Request / Location", 10, bold=True)
        text(e, x + w - 193, y + 117, "Status / Priority / Age", 10, bold=True)
        for i, (label, status) in enumerate(
            [
                ("Kitchen leak", "Waiting / High / 2 days"),
                ("Entry light", "Open / Normal / 1 day"),
                ("Roof inspection", "Scheduled / Normal / 3 days"),
            ]
        ):
            yy = y + 128 + i * 51
            rect(e, x, yy, w, 44, YELLOW if i == 0 else "#ffffff")
            text(e, x + 10, yy + 17, label, 11, bold=True)
            text(e, x + 10, yy + 34, "Maple Court / Unit A", 9)
            text(e, x + w - 193, yy + 24, status, 9)


def detail(e, x, y, w, phone):
    text(e, x, y, "Kitchen leak", 18, bold=True)
    text(e, x, y + 23, "Maple Court / Unit A / Request 104", 10)
    note(e, x, y + 39, "Waiting - replacement part", "Assigned: RHP team / Follow-up: reviewed", w)
    text(e, x, y + 112, "Tenant-authorized entry: Yes", 11, bold=True)
    text(e, x, y + 132, "RHP staff and assigned repair professionals", 9)
    button(e, x, y + 147, "Add update", 115)
    button(e, x + 128, y + 147, "Manage work", 116)
    yy = y + 207
    text(e, x, yy, "Conversation", 13, bold=True)
    text(e, x, yy + 23, "Oct 17 / Tenant / Water below the sink.", 10)
    text(e, x, yy + 44, "Oct 17 / RHP / Part ordered; update tomorrow.", 10)
    if phone:
        text(e, x, yy + 77, "Work history: Open > Waiting", 10)
        line(e, x, yy + 97, x + w, yy + 97, dash=True)
        text(e, x, yy + 119, "Staff only / Internal notes (1)", 11, bold=True)
        text(e, x, yy + 145, "+ Expenses and recharges", 10)
        text(e, x, yy + 171, "+ Email delivery and revisions", 10)
    else:
        line(e, x, yy + 59, x + w, yy + 59, dash=True)
        text(e, x, yy + 80, "Staff only: Internal notes (1)    |    Work history (2)", 10)
        text(e, x, yy + 102, "+ Expenses and recharges    + Email delivery and revisions", 9)


def tenant(e, x, y, w, phone):
    text(e, x, y, "Maintenance", 18, bold=True)
    text(e, x, y + 27, "1 active request", 14, bold=True)
    button(e, x, y + 43, "Request maintenance", 159)
    note(e, x, y + 91, "Kitchen leak - Waiting", "Unit A / Updated Oct 17, 2026", w)
    text(e, x + 11, y + 166, "Part ordered. RHP will update you tomorrow.", 10)
    button(e, x, y + 185, "View request", 120)
    line(e, x, y + 239, x + w, y + 239)
    text(e, x, y + 267, "+ Completed request history (3)", 11, bold=True)
    if phone:
        text(e, x, y + 321, "Not an emergency-dispatch service.", 10)
        text(e, x, y + 340, "For immediate danger, call 911.", 10)
        text(e, x, y + 359, "Contact RHP directly for urgent problems.", 10)
    else:
        text(
            e,
            x,
            y + 309,
            "Not emergency dispatch. For immediate danger, call 911. "
            "Contact RHP for urgent problems.",
            10,
        )


def ledger(e, x, y, w, phone):
    text(e, x, y, "Lease account / Unit A", 18, bold=True)
    text(e, x, y + 23, "Maple Court / Example tenancy / Active / Open", 10)
    if phone:
        for i, value in enumerate(
            [
                "Due now: $0.00",
                "Past due: $0.00",
                "Upcoming: $840.00 / Nov 5, 2026",
                "Account balance: $840.00",
            ]
        ):
            text(e, x, y + 59 + i * 24, value, 11, bold=i in (0, 3))
        text(e, x, y + 155, "Includes upcoming charges", 9)
        button(e, x, y + 174, "Record payment")
        text(e, x, y + 231, "Transactions", 13, bold=True)
        text(e, x, y + 260, "Nov 1 / Rent / Upcoming", 11, bold=True)
        text(e, x, y + 281, "Charge $900.00 / Corrected $840.00", 10)
        text(e, x + 10, y + 303, "Credit adjustment -$60.00", 10, fill=GREEN)
        text(e, x + 10, y + 323, "Nov 2 / Agreed repair concession", 9)
        text(e, x, y + 350, "Running balance: $840.00", 11, bold=True)
        text(e, x, y + 394, "+ Corrections and audit history", 10)
    else:
        col = w / 4
        for i, (label, value) in enumerate(
            [
                ("Due now", "$0.00"),
                ("Past due", "$0.00"),
                ("Upcoming", "$840.00"),
                ("Account balance", "$840.00"),
            ]
        ):
            text(e, x + i * col, y + 54, label, 9)
            text(e, x + i * col, y + 76, value, 15, bold=True)
        text(e, x, y + 99, "Upcoming Nov 5, 2026 / Account balance includes upcoming charges", 9)
        button(e, x, y + 115, "Record payment", 130)
        button(e, x + 142, y + 115, "Add one-time charge", 151)
        text(e, x, y + 173, "Date / Description", 10, bold=True)
        text(e, x + w - 252, y + 173, "Charge     Payment/credit     Balance", 10, bold=True)
        line(e, x, y + 183, x + w, y + 183)
        text(e, x, y + 204, "Nov 1 / Rent / Upcoming", 10)
        text(e, x + w - 252, y + 204, "$840.00               -              $840.00", 10)
        text(e, x + 10, y + 226, "Original $900.00 / Credit adjustment -$60.00", 9, fill=GREEN)
        text(e, x + 10, y + 243, "Nov 2 / Agreed repair concession", 9)
        line(e, x, y + 255, x + w, y + 255)
        text(e, x, y + 282, "+ Corrections and audit history", 10)


def concept(key, title):
    pages = []
    for screen, label, draw in [
        ("queue", "Staff queue", queue),
        ("detail", "Request detail", detail),
        ("tenant", "Tenant maintenance", tenant),
        ("ledger", "Lease ledger", ledger),
    ]:
        for phone in (False, True):
            elements = []
            x, y, w = shell(elements, key, screen, phone)
            if key == "operations-desk" and screen == "queue" and not phone:
                detail(elements, x, y, w, phone)
            else:
                draw(elements, x, y, w, phone)
            pages.append(
                {
                    "title": f"{title} / {label}",
                    "subtitle": (
                        f"{'Phone' if phone else 'Desktop'} layout study - not a shipped screen"
                    ),
                    "width": 612 if phone else 792,
                    "height": 792 if phone else 612,
                    "elements": elements,
                }
            )
    return {"title": title, "pages": pages}


def diagrams():
    e = []
    text(e, 40, 108, "Different roles, different navigation", 14, bold=True)
    for x, title, entries in [
        (
            40,
            "Manager / Administrator",
            [
                "Portfolio: properties, units, leases",
                "Money: Rent & Payments, recoveries",
                "Work: maintenance, vendors",
                "Documents and tenant operations",
            ],
        ),
        (
            412,
            "Tenant",
            [
                "Home and current lease",
                "Payments statement and documents",
                "Maintenance: active + history",
                "Account controls",
            ],
        ),
    ]:
        rect(e, x, 130, 340, 170)
        text(e, x + 15, 154, title, 13, bold=True)
        for i, entry in enumerate(entries):
            text(e, x + 15, 185 + i * 27, entry, 11)
    line(e, 210, 302, 210, 346)
    line(e, 582, 302, 582, 346)
    rect(e, 40, 346, 712, 74)
    text(e, 55, 372, "Object context: Overview / Conversation / Work / Evidence", 13, bold=True)
    text(e, 55, 397, "Show only authorized sections. Worker access remains assigned-work only.", 11)
    text(
        e,
        40,
        463,
        "Global menu = domain. Local menu = current object. Account = separate controls.",
        11,
    )
    nav = {
        "title": "Role-aware navigation",
        "pages": [{"title": "RHP navigation map", "elements": e}],
    }
    e = []
    for x, label, sub in [
        (40, "Request", "Property + optional unit"),
        (289, "Work tracking", "Assignment + status"),
        (538, "Repair expense", "Recorded, not tenant liability"),
    ]:
        rect(e, x, 140, 214, 90)
        text(e, x + 13, 170, label, 14, bold=True)
        text(e, x + 13, 198, sub, 10)
    line(e, 254, 183, 284, 183)
    text(e, 266, 176, ">", 12)
    line(e, 503, 183, 533, 183)
    text(e, 515, 176, ">", 12)
    text(e, 40, 280, "Conversations remain tenancy-specific. Internal notes remain staff-only.", 11)
    line(e, 645, 230, 645, 336, dash=True)
    text(e, 435, 311, "Separate, explicit manager decision", 11, bold=True)
    rect(e, 413, 336, 339, 103)
    text(e, 430, 365, "Prepare recharge > Review > Confirm", 13, bold=True)
    text(e, 430, 390, "Eligible tenancy / manual amount / due date", 10)
    text(e, 430, 414, "Post through the existing ledger service", 10)
    text(
        e,
        40,
        483,
        "No automatic liability. No inferred allocation. No vendor payment or general ledger.",
        11,
    )
    flow = {
        "title": "Maintenance and money",
        "pages": [{"title": "Maintenance workflow boundaries", "elements": e}],
    }
    return {"navigation": nav, "maintenance-workflow": flow}


def main():
    books = {
        key: concept(key, label)
        for key, label in [
            ("portfolio-workspace", "A - Portfolio workspace"),
            ("operations-desk", "B - Operations desk"),
            ("calm-portal", "C - Calm portal"),
        ]
    }
    books.update(diagrams())
    sources, outputs = HERE / "sources", HERE / "artifacts"
    sources.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    for name, book in books.items():
        (sources / f"{name}.json").write_text(json.dumps(book, indent=2) + "\n")
        for grayscale in (False, True):
            renderer.render(book, outputs / name, grayscale=grayscale)
            stem = outputs / (name + ("-grayscale" if grayscale else ""))
            subprocess.run(  # noqa: S603
                ["pdftoppm", "-scale-to", "1600", "-png", str(stem) + ".pdf", str(stem)],  # noqa: S607
                check=True,
            )


if __name__ == "__main__":
    main()
