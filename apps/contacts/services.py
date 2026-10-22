"""Operations on people, including the one optional portal link.

A person is master data. Linking a portal account is a named act: it updates the person
and every lease membership that mirrors the link, so portal scoping cannot drift from the
person it belongs to (ADR-029 D2).
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.contacts.models import Person


def person_for_user(user, *, phone=""):
    """The person row for a tenant account, created from the account on first use."""
    person = Person.objects.filter(portal_user=user).first()
    if person is not None:
        return person
    # A username is a usable display name when the account has no real one; the person
    # constraint requires a name and "Unnamed" rows are not useful on a lease.
    first_name = user.first_name or (user.username if not user.last_name else "")
    return Person.objects.create(
        first_name=first_name,
        last_name=user.last_name,
        email=user.email,
        phone=phone,
        portal_user=user,
    )


@transaction.atomic
def link_portal_account(person: Person, user, *, actor=None) -> Person:
    """Give one person the portal account, and mirror it on their lease memberships."""
    if user.role != "TENANT":
        raise ValidationError("Only a tenant account can be a person's portal login.")
    if not user.is_active:
        raise ValidationError("Activate the account before linking it to a person.")
    existing = getattr(user, "person", None)
    if existing is not None and existing.pk != person.pk:
        raise ValidationError("That account already belongs to another person.")
    person = Person.objects.select_for_update().get(pk=person.pk)
    person.portal_user = user
    person.save(update_fields=["portal_user", "updated_at"])
    person.lease_memberships.update(tenant=user)
    return person
