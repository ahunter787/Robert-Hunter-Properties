"""Print the B1 control picture: trial balance, AR tie and unposted source events."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounting import services

ZERO = Decimal("0.00")


class Command(BaseCommand):
    help = "Show the B1 trial balance and the AR-control tie to the tenant sub-ledger."

    def handle(self, *args, **options):
        rows = services.trial_balance()
        self.stdout.write("Trial balance")
        for row in rows:
            self.stdout.write(
                f"  {row['account'].code} {row['account'].name:<40} "
                f"Dr {row['debit']:>10}  Cr {row['credit']:>10}"
            )
        debit = sum((row["debit"] for row in rows), ZERO)
        credit = sum((row["credit"] for row in rows), ZERO)
        self.stdout.write(f"  totals: Dr {debit}  Cr {credit}")

        tie = services.ar_control_tie()
        self.stdout.write(
            f"\nAR control {tie['control']}  sub-ledger {tie['subledger']}  "
            f"difference {tie['difference']}"
        )
        if tie["difference"] != ZERO:
            self.stderr.write(self.style.ERROR("AR control does not tie to the tenant ledger."))

        deposit = services.deposit_control_tie()
        self.stdout.write(
            f"Deposit liability {deposit['control']}  register {deposit['register']}  "
            f"difference {deposit['difference']}"
        )
        if deposit["difference"] != ZERO:
            self.stdout.write(
                "  (a pending retained-deposit disposition is the expected difference until E6)"
            )

        missing = services.unposted_count()
        self.stdout.write(f"unposted source events: {missing}")
        if missing:
            self.stderr.write(
                self.style.ERROR("Run `manage.py accounting_sync` to post the missing events.")
            )
