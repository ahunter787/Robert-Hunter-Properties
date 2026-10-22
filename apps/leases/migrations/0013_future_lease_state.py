"""A tenancy that has not started is upcoming, not active (M2, ADR-029 D1).

The status choices gain ``FUTURE``; the data step only corrects the rows the old model got
wrong — an ``ACTIVE`` lease whose term has not begun. The reverse leaves ``FUTURE`` rows as
they are: restoring a stale ``ACTIVE`` label would be a different lie, and the value is still
readable as data.
"""

from django.db import migrations, models
from django.utils import timezone


def schedule_future_leases(apps, schema_editor):
    Lease = apps.get_model("leases", "Lease")
    database = schema_editor.connection.alias
    today = timezone.localdate()
    Lease.objects.using(database).filter(status="ACTIVE", start_date__gt=today).update(
        status="FUTURE"
    )


def leave_as_is(apps, schema_editor):
    """The reverse does not relabel a scheduled tenancy as active."""


class Migration(migrations.Migration):
    dependencies = [
        ("leases", "0012_retire_e4_onboarding"),
    ]

    operations = [
        migrations.RunPython(schedule_future_leases, leave_as_is),
        migrations.AlterField(
            model_name="lease",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("FUTURE", "Upcoming"),
                    ("ACTIVE", "Active"),
                    ("ENDED", "Ended"),
                ],
                db_index=True,
                default="DRAFT",
                help_text=(
                    "Draft until staff activate it; upcoming until the term starts; ended is "
                    "history and read-only."
                ),
                max_length=10,
            ),
        ),
    ]
