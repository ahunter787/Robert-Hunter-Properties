"""Create a tenant account, optionally emailing its invitation."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts import emails
from apps.accounts.models import Role, TenantProfile, User


class Command(BaseCommand):
    help = "Create a tenant account (and send its invitation unless suppressed)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", required=True, help="Invitation address.")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument("--phone", default="")
        parser.add_argument(
            "--no-email",
            action="store_true",
            help="Create the account without sending an invitation.",
        )
        parser.add_argument(
            "--base-url",
            default="http://localhost:8000",
            help="Base URL used to print the invitation link.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f"An account named {username!r} already exists.")

        user = User.objects.create_user(
            username=username,
            email=options["email"],
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=Role.TENANT,
        )
        TenantProfile.objects.create(user=user, phone=options["phone"])
        self.stdout.write(
            self.style.SUCCESS(f"Created tenant {user.username} (id={user.pk}, role={user.role})")
        )

        if options["no_email"]:
            self.stdout.write("No invitation sent (--no-email).")
            return

        base_url = options["base_url"]
        delivered = emails.send_invitation(user, base_url)
        if delivered:
            self.stdout.write(f"Invitation emailed to {user.email}.")
        else:
            self.stdout.write(
                self.style.WARNING("Console email backend: nothing was delivered. Invitation link:")
            )
            self.stdout.write(f"  {emails.invitation_url(user, base_url)}")
