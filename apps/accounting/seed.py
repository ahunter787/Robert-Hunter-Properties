"""Idempotent chart seeding, shared by the management command and test setup.

The data migration remains the production seed; this module exists so a flushed test
database (transaction=True tests) can be brought back to the same chart without hand-coded
accounts in each test.
"""

from apps.accounting.models import AccountMapping, ChartAccount

ACCOUNTS = [
    ("1110", "Operating bank", "ASSET", "DEBIT", True, True),
    ("1120", "Deposit/escrow bank", "ASSET", "DEBIT", True, True),
    ("1450", "Undeposited funds", "ASSET", "DEBIT", True, True),
    ("1200", "Tenant accounts receivable", "ASSET", "DEBIT", True, True),
    ("2100", "Accounts payable", "LIABILITY", "CREDIT", True, True),
    ("2300", "Security deposits held", "LIABILITY", "CREDIT", True, True),
    ("2400", "Tenant credits held", "LIABILITY", "CREDIT", True, True),
    ("3000", "Owner's equity", "EQUITY", "CREDIT", True, False),
    ("3070", "Opening balance equity", "EQUITY", "CREDIT", True, False),
    ("3100", "Owner draws/contributions", "EQUITY", "DEBIT", True, False),
    ("4000", "Rent income", "INCOME", "CREDIT", False, False),
    ("4100", "NNN recoveries", "INCOME", "CREDIT", False, False),
    ("4200", "Utility recoveries", "INCOME", "CREDIT", False, False),
    ("4300", "Maintenance recoveries", "INCOME", "CREDIT", False, False),
    ("4350", "Deposit forfeitures and damage recoveries", "INCOME", "CREDIT", False, False),
    ("4900", "Late fees and other income", "INCOME", "CREDIT", False, False),
    ("5000", "Repairs and maintenance", "EXPENSE", "DEBIT", False, False),
    ("5100", "Utilities", "EXPENSE", "DEBIT", False, False),
    ("5200", "Property taxes", "EXPENSE", "DEBIT", False, False),
    ("5300", "Insurance", "EXPENSE", "DEBIT", False, False),
    ("5400", "Mortgage interest", "EXPENSE", "DEBIT", False, False),
    ("5500", "Professional and administrative", "EXPENSE", "DEBIT", False, False),
    ("5600", "HOA dues", "EXPENSE", "DEBIT", False, False),
    ("5700", "Bad debt", "EXPENSE", "DEBIT", False, False),
    ("5900", "Other expenses", "EXPENSE", "DEBIT", False, False),
]

MAPPINGS = [
    ("charge.RENT", "4000"),
    ("charge.NNN", "4100"),
    ("charge.UTILITY", "4200"),
    ("charge.MAINTENANCE", "4300"),
    ("charge.OTHER", "4900"),
    ("charge.MANUAL", "4900"),
    ("charge.DEFAULT", "4900"),
    ("write_off", "5700"),
]


def seed_defaults():
    by_code = {}
    for code, name, kind, normal, system, control in ACCOUNTS:
        account, _ = ChartAccount.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "kind": kind,
                "normal_side": normal,
                "is_system": system,
                "is_control": control,
                "is_active": True,
            },
        )
        by_code[code] = account
    for event_key, code in MAPPINGS:
        AccountMapping.objects.update_or_create(
            event_key=event_key, defaults={"account": by_code[code]}
        )
