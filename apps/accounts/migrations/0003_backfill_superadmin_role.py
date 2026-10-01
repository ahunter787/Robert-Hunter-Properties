"""Backfill SUPERADMIN for accounts that were already Django superusers.

Phase 0 shipped identities with no role. Anyone who was already a superuser is by
definition an RHP superadmin, so the portal behaves the same for them before and
after this migration.
"""

from django.db import migrations

SUPERADMIN = "SUPERADMIN"


def forwards(apps, schema_editor):
    user_model = apps.get_model("accounts", "User")
    user_model.objects.filter(is_superuser=True).exclude(role=SUPERADMIN).update(role=SUPERADMIN)


def backwards(apps, schema_editor):
    """No-op: reverting the schema is enough, and roles are not destroyed."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_phase1_roles_profiles_throttle"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
