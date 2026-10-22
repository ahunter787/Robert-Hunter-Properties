"""A lease party is a person; a portal login is optional (M2b, ADR-029 D2).

Every existing tenant account becomes one ``contacts.Person``, and each membership keeps
the login it already had as that membership's optional portal link. A co-occupant or
guarantor can then be recorded without an account. The reverse keeps the people and the
membership roles; it cannot invent a login for a party that has none.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_people(apps, schema_editor):
    Person = apps.get_model("contacts", "Person")
    User = apps.get_model("accounts", "User")
    TenantProfile = apps.get_model("accounts", "TenantProfile")
    Membership = apps.get_model("leases", "LeaseTenant")
    database = schema_editor.connection.alias

    people = {}
    for person in Person.objects.using(database).all().iterator():
        people[(person.email.lower(), person.first_name, person.last_name)] = person

    def person_for(user):
        key = (user.email.lower(), user.first_name, user.last_name)
        if key in people:
            return people[key]
        profile = (
            TenantProfile.objects.using(database).filter(user_id=user.pk).first()
        )
        first_name = user.first_name or (user.username if not user.last_name else "")
        person = Person.objects.using(database).create(
            first_name=first_name,
            last_name=user.last_name,
            email=user.email,
            phone=profile.phone if profile else "",
            portal_user_id=user.pk,
        )
        people[key] = person
        return person

    for user in User.objects.using(database).filter(role="TENANT").iterator():
        person_for(user)

    for membership in Membership.objects.using(database).all().iterator():
        if membership.person_id is not None or membership.tenant_id is None:
            continue
        user = User.objects.using(database).get(pk=membership.tenant_id)
        membership.person_id = person_for(user).pk
        membership.role = "TENANT"
        membership.save(update_fields=["person", "role"])


def keep_people(apps, schema_editor):
    """The reverse does not delete person rows or relink logins."""


class Migration(migrations.Migration):
    # Person rows are inserted and then referenced by a new non-null column; PostgreSQL
    # cannot both queue trigger events for that table and alter the referencing table in
    # one transaction, so each step commits on its own.
    atomic = False

    dependencies = [
        ("contacts", "0001_lease_people"),
        ("leases", "0013_future_lease_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="leasetenant",
            options={
                "ordering": (
                    "-is_primary",
                    "person__last_name",
                    "person__first_name",
                    "person__pk",
                )
            },
        ),
        migrations.RemoveConstraint(model_name="leasetenant", name="tenant_once_per_lease"),
        migrations.AddField(
            model_name="leasetenant",
            name="person",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lease_memberships",
                to="contacts.person",
            ),
        ),
        migrations.AddField(
            model_name="leasetenant",
            name="role",
            field=models.CharField(
                choices=[
                    ("TENANT", "Tenant"),
                    ("ADULT_OCCUPANT", "Adult occupant"),
                    ("GUARANTOR", "Guarantor"),
                    ("AUTHORIZED_CONTACT", "Authorized contact"),
                ],
                default="TENANT",
                help_text=(
                    "Tenant, adult occupant, guarantor or authorized contact."
                ),
                max_length=20,
            ),
        ),
        migrations.RunPython(create_people, keep_people),
        migrations.AlterField(
            model_name="leasetenant",
            name="person",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lease_memberships",
                to="contacts.person",
            ),
        ),
        migrations.AlterField(
            model_name="leasetenant",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional portal login for this membership.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lease_memberships",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="leasetenant",
            constraint=models.UniqueConstraint(
                fields=("lease", "person"), name="person_once_per_lease"
            ),
        ),
    ]
