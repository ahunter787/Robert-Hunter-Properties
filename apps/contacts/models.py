"""People who live on leases, separate from the logins that may represent them.

A tenancy party is a person: a tenant, an adult occupant, a guarantor or an authorised
contact. The portal login is an optional permission on that person's membership of a
lease, not the person's identity (ADR-029 D2, informed by the contact-plus-optional-
portal-access model in established property-management products). ``accounts.User``
remains the only authentication model; this table is master data.

No person is created for staff accounts. A person without a login is a real person on a
lease and simply has no portal access; the membership can link an account when one exists.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Person(models.Model):
    """One human being RHP deals with as a tenant or lease contact."""

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField("phone number", max_length=32, blank=True)
    #: The one optional portal login for this person. A lease membership mirrors this
    #: link; access is never inferred from an email address.
    portal_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="person",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "pk")
        verbose_name_plural = "people"
        constraints = [
            models.CheckConstraint(
                condition=~Q(first_name="", last_name=""),
                name="person_has_a_name",
            ),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email or "Unnamed person"

    def clean(self):
        super().clean()
        if not self.first_name.strip() and not self.last_name.strip():
            raise ValidationError("Give this person a first or last name.")
