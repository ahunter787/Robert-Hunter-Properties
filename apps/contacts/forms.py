"""Plain forms for the people screen.

A person exists without an account; an account is an optional login attached later. The
creation form can do both in one reviewed step, which is how a new tenant is usually
taken on (ADR-029 D2).
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.common.forms import StyledForm, StyledModelForm
from apps.contacts.models import Person


class PersonForm(StyledModelForm):
    class Meta:
        model = Person
        fields = ["first_name", "last_name", "email", "phone"]

    def clean(self):
        cleaned = super().clean()
        if (
            not (cleaned.get("first_name") or "").strip()
            and not (cleaned.get("last_name") or "").strip()
        ):
            self.add_error("first_name", "Give this person a first or last name.")
        return cleaned


class PersonCreateForm(PersonForm):
    """A person, optionally with a portal login and invitation in the same step."""

    give_portal_access = forms.BooleanField(
        required=False,
        label="Give them a portal login",
        help_text="Creates an inactive tenant account and emails an invitation.",
    )
    username = forms.CharField(
        max_length=150,
        required=False,
        help_text="Used to sign in. Letters, digits and @/./+/-/_ only.",
    )

    class Meta(PersonForm.Meta):
        fields = ["first_name", "last_name", "email", "phone"]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("give_portal_access"):
            return cleaned
        from apps.accounts.models import User

        email = (cleaned.get("email") or "").strip().lower()
        username = (cleaned.get("username") or "").strip()
        if not email:
            self.add_error("email", "A portal login needs an email address.")
        elif User.objects.filter(email__iexact=email).exists():
            self.add_error("email", "An account already uses that email address.")
        if not username:
            self.add_error("username", "Choose a username for the login.")
        elif User.objects.filter(username__iexact=username).exists():
            self.add_error("username", "That username is already taken.")
        cleaned["email"] = email
        cleaned["username"] = username
        return cleaned


class LinkAccountForm(StyledForm):
    """Attach an existing tenant account to a person who has none."""

    user = forms.ModelChoiceField(queryset=None, label="Tenant account")

    def __init__(self, *args, person, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import Role, User

        self.fields["user"].queryset = (
            User.objects.filter(role=Role.TENANT, is_active=True)
            .exclude(person__isnull=False)
            .order_by("first_name", "last_name", "username")
        )

    def clean_user(self):
        user = self.cleaned_data["user"]
        if user.role != "TENANT":
            raise ValidationError("Only a tenant account can be linked to a person.")
        return user
