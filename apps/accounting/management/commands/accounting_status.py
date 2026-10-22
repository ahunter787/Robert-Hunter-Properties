"""Print the B1 control picture: trial balance, AR tie and unposted source events."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounting import services
from apps.accounting.models import JournalEntry
from apps.ledger.models import Charge, FundsApplication, Payment, PaymentKind, PaymentStatus

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

        missing = 0
        missing += sum(
            1
            for charge in Charge.objects.all()
            if not JournalEntry.objects.filter(source_key=f"charge:{charge.pk}:created").exists()
        )
        for payment in Payment.objects.all():
            if payment.kind == PaymentKind.REVERSAL:
                key = f"payment:{payment.reverses_id}:reversed"
            elif payment.status == PaymentStatus.CLEARED:
                key = f"payment:{payment.pk}:recorded"
            else:
                continue
            if not JournalEntry.objects.filter(source_key=key).exists():
                missing += 1
        for application in FundsApplication.objects.all():
            transition = "released" if application.reverses_id else "applied"
            if not JournalEntry.objects.filter(
                source_key=f"application:{application.pk}:{transition}"
            ).exists():
                missing += 1
        self.stdout.write(f"unposted source events: {missing}")
        if missing:
            self.stderr.write(
                self.style.ERROR("Run `manage.py accounting_sync` to post the missing events.")
            )
