"""Post every existing kernel source event to the GL, idempotently.

B1 arrives after the tenant sub-ledger already has history. This command is the safe bridge:
it walks charges, payments and credit applications and calls the same posting service the
live paths use. Re-running is a no-op because every journal has a unique source key.
"""

from django.core.management.base import BaseCommand

from apps.accounting import services
from apps.ledger.models import Charge, FundsApplication, Payment, PaymentKind, PaymentStatus


class Command(BaseCommand):
    help = "Post existing charges, payments and credit applications to the general ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what is missing without writing."
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        posted = 0
        already = 0
        skipped = 0

        def post(key, function):
            nonlocal posted, already, skipped
            from apps.accounting.models import JournalEntry

            if JournalEntry.objects.filter(source_key=key).exists():
                already += 1
                return
            if dry:
                posted += 1
                return
            if function() is None:
                skipped += 1
            else:
                posted += 1

        charges = Charge.objects.select_related("lease__unit__property", "adjusts").order_by("pk")
        for charge in charges:
            post(
                f"charge:{charge.pk}:created",
                lambda charge=charge: services.post_charge(charge),
            )

        for payment in Payment.objects.select_related("lease__unit__property").order_by("pk"):
            if payment.kind == PaymentKind.REVERSAL:
                original = payment.reverses
                if original is None:
                    skipped += 1
                    continue
                post(
                    f"payment:{original.pk}:reversed",
                    lambda original=original: services.post_payment(
                        original, transition="reversed"
                    ),
                )
            elif payment.status == PaymentStatus.CLEARED:
                post(
                    f"payment:{payment.pk}:recorded",
                    lambda payment=payment: services.post_payment(payment, transition="recorded"),
                )
            else:
                skipped += 1

        for application in FundsApplication.objects.select_related(
            "lease__unit__property", "source_charge", "reverses"
        ).order_by("pk"):
            transition = "released" if application.reverses_id else "applied"
            post(
                f"application:{application.pk}:{transition}",
                lambda application=application: services.post_application(application),
            )

        verb = "would post" if dry else "posted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {posted}; already present {already}; not postable {skipped}."
            )
        )
