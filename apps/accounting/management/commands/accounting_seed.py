from django.core.management.base import BaseCommand

from apps.accounting.seed import seed_defaults


class Command(BaseCommand):
    help = "Ensure the B1 chart and event mappings exist (idempotent)."

    def handle(self, *args, **options):
        seed_defaults()
        self.stdout.write(self.style.SUCCESS("Chart and mappings are present."))
