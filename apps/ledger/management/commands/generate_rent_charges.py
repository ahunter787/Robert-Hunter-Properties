"""Create the missing monthly rent and NNN charges for active leases.

Idempotent: a month that has already been charged is left alone, so this can run
on a schedule (Phase 12) as safely as it runs by hand. The management screen has
the same action for one lease at a time. The command keeps its name, which is what
operators and cron entries already call.
"""

import datetime as dt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.common.dates import due_date_in
from apps.leases.models import Lease, LeaseTemplate
from apps.ledger import services
from apps.ledger.models import ChargeKind


class Command(BaseCommand):
    help = "Create the monthly rent (and NNN) charges that are missing for active leases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=None,
            help=(
                "Charge through this many months beyond the current month "
                "(default: RHP_CHARGE_HORIZON_MONTHS)."
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
            due_dates = services.rent_due_dates(lease, through=through)
            if options["dry_run"]:
                missing = self._missing(lease, due_dates)
                would_create += missing
                if missing:
                    self.stdout.write(f"{lease}: {missing} charge(s) missing")
                continue

            created = services.generate_charges(lease, through=through)
            created_total += len(created)

        horizon = f"{through:%B %Y}"
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {would_create} charge(s) would be created through {horizon}."
                )
            )
            return
        if created_total:
            self.stdout.write(
                self.style.SUCCESS(f"{created_total} charge(s) created through {horizon}.")
            )
        else:
            self.stdout.write(f"Nothing to do: charges are raised through {horizon}.")

    def _missing(self, lease, due_dates) -> int:
        """How many charges of any kind this lease is missing through the horizon."""
        rent = set(lease.charges.rent().values_list("due_date", flat=True))
        nnn = set(lease.charges.filter(kind=ChargeKind.NNN).values_list("due_date", flat=True))
        shared = set(
            lease.charges.filter(kind=ChargeKind.RESPONSIBILITY).values_list(
                "responsibility_id", "due_date"
            )
        )
        missing = sum(1 for due in due_dates if due not in rent)
        if lease.template == LeaseTemplate.NNN:
            missing += sum(1 for due in due_dates if due not in nnn and lease.nnn_for(due) > 0)
        for due in due_dates:
            for responsibility, _amount in services.responsibilities_due(lease, due):
                if (responsibility.pk, due) not in shared:
                    missing += 1
        return missing

    def _horizon(self, options) -> dt.date:
        if options["through"]:
            try:
                year, month = (int(part) for part in options["through"].split("-"))
                return due_date_in(year, month, 31)
            except (ValueError, TypeError) as exc:
                raise CommandError("--through takes a month, as YYYY-MM.") from exc
        months = options["months"]
        if months is None:
            months = settings.RHP_CHARGE_HORIZON_MONTHS
        return services.generation_horizon(months)
