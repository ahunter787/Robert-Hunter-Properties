"""Start every scheduled tenancy whose start date has arrived (M2, ADR-029 D1).

Idempotent: a tenancy already active is untouched, so this can run at deploy and as often as
an operator likes. The manager and tenant screens also self-heal by calling the same service,
because RHP has no task queue.
"""

from django.core.management.base import BaseCommand

from apps.leases import services


class Command(BaseCommand):
    help = "Start upcoming tenancies whose term has begun."

    def handle(self, *args, **options):
        activated = services.activate_due_leases()
        if not activated:
            self.stdout.write("No scheduled tenancy is due to start.")
            return
        for result in activated:
            self.stdout.write(f"Started tenancy {result.lease.unit.label} ({result.lease.pk}).")
        self.stdout.write(self.style.SUCCESS(f"{len(activated)} tenancy(ies) started."))
