"""Create the missing monthly rent charges for active leases.

Idempotent: a month that has already been charged is left alone, so this can run
on a schedule (Phase 12) as safely as it runs by hand. The management screen has
the same action for one lease at a time.
"""

import datetime as dt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.common.dates import due_date_in
from apps.leases.models import Lease
from apps.ledger import services


class Command(BaseCommand):
    help = "Create the monthly rent charges that are missing for active leases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=None,
            help=(
                "Charge through this many months beyond the current month "
                "(default: RHP_RENT_CHARGE_HORIZON_MONTHS)."
            ),
        )
        parser.add_argument(
            "--through",
            metavar="YYYY-MM",
            help="Charge through the end of this month instead of a month count.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without creating it.",
        )

    def handle(self, *args, **options):
        through = self._horizon(options)
        leases = Lease.objects.active().select_related("unit__property")

        created_total = 0
        would_create = 0
        for lease in leases:
            if options["dry_run"]:
                existing = set(lease.charges.rent().values_list("due_date", flat=True))
                missing = [
                    due
                    for due in services.rent_due_dates(lease, through=through)
                    if due not in existing
                ]
                would_create += len(missing)
                if missing:
                    self.stdout.write(f"{lease}: {len(missing)} charge(s) missing")
                continue

            created = services.generate_rent_charges(lease, through=through)
            created_total += len(created)

        horizon = f"{through:%B %Y}"
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {would_create} rent charge(s) would be created through {horizon}."
                )
            )
            return
        if created_total:
            self.stdout.write(
                self.style.SUCCESS(f"{created_total} rent charge(s) created through {horizon}.")
            )
        else:
            self.stdout.write(f"Nothing to do: rent is charged through {horizon}.")

    def _horizon(self, options) -> dt.date:
        if options["through"]:
            try:
                year, month = (int(part) for part in options["through"].split("-"))
                return due_date_in(year, month, 31)
            except (ValueError, TypeError) as exc:
                raise CommandError("--through takes a month, as YYYY-MM.") from exc
        months = options["months"]
        if months is None:
            months = settings.RHP_RENT_CHARGE_HORIZON_MONTHS
        return services.generation_horizon(months)
