"""Clear recorded login attempts for an account or an address.

The support path when a legitimate user has locked themselves out (the throttle
is described in docs/security.md).
"""

from django.core.management.base import BaseCommand

from apps.accounts.throttle import LoginThrottle


class Command(BaseCommand):
    help = "Clear login attempts for a username, or for an IP address with --ip."

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="Username, or an IP address with --ip.")
        parser.add_argument(
            "--ip", action="store_true", help="Treat the identifier as an IP address."
        )

    def handle(self, *args, **options):
        throttle = LoginThrottle()
        identifier = options["identifier"]
        deleted = (
            throttle.reset(ip=identifier) if options["ip"] else throttle.reset(username=identifier)
        )

        if not deleted:
            self.stdout.write("No matching login attempts; nothing to do.")
            return
        self.stdout.write(self.style.SUCCESS(f"Cleared {deleted} login attempt(s)."))
