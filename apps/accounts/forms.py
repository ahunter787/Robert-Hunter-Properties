"""Forms for RHP identity screens.

Every form inherits :class:`~apps.common.forms.StyledForm` so templates can
render ``{{ field }}`` without repeating design-system classes, and so
server-side validation messages stay in one place.
"""

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import ValidationError

from apps.accounts.models import TenantProfile, User
from apps.accounts.throttle import LoginThrottle, client_ip
from apps.common.forms import (  # noqa: F401 - re-exported for existing imports
    StyledForm,
    StyledModelForm,
)
from apps.common.images import validate_image_upload


class StyledAuthenticationForm(StyledForm, AuthenticationForm):
    """Login form with the design-system styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Django renders these as bare inputs; give them the RHP look and the
        # right autocomplete hints for password managers.
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "autocomplete": "username", "placeholder": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password", "placeholder": "password"}
        )


class ThrottledLoginForm(StyledAuthenticationForm):
    """Refuses to authenticate while the account or address is throttled.

    The check runs *before* authentication so a locked-out attacker does not even
    reach the password hasher, and the message never reveals whether the account
    exists.
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "throttled": (
            "Too many unsuccessful sign-in attempts. Please wait a few minutes and try again."
        ),
    }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        self.request = request
        self.throttle = LoginThrottle()
        self.client_ip = client_ip(request) if request is not None else None

    def clean(self):
        submitted = (self.data.get("username") or "").strip()
        if submitted and self.throttle.state(submitted, self.client_ip).locked:
            raise ValidationError(self.error_messages["throttled"], code="throttled")
        return super().clean()

    @staticmethod
    def is_throttle_error(form) -> bool:
        """True when a form failed because of the throttle, not bad credentials."""
        return any(
            getattr(error, "code", None) == "throttled"
            for errors in form.errors.as_data().values()
            for error in errors
        )


class ProfileForm(StyledModelForm):
    """Tenant-editable contact details. ``notes`` is staff-only and excluded."""

    class Meta:
        model = TenantProfile
        fields = ["phone", "preferred_contact_method"]
        labels = {
            "phone": "Phone number",
            "preferred_contact_method": "Preferred contact method",
        }


class TenantProfileForm(StyledModelForm):
    """The staff-side edit of a tenant's photo.

    Contact details are the tenant's own to change on their account page; this
    form exists so staff can put a face to a name, and deliberately edits nothing
    else.
    """

    remove_photo = forms.BooleanField(
        required=False,
        label="Remove the current photo",
        help_text="Uploading a new photo replaces the current one.",
    )

    class Meta:
        model = TenantProfile
        fields = ["photo"]
        labels = {"photo": "Photo"}
        help_texts = {"photo": "JPEG, PNG, or WebP."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.pk and self.instance.photo):
            self.fields.pop("remove_photo")

    def clean_photo(self):
        return validate_image_upload(
            self.cleaned_data.get("photo"),
            max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024,
        )

    def clean(self):
        cleaned = super().clean()
        # Only a *fresh* upload conflicts with removal: on an edit form the field
        # still holds the file already on disk, which is truthy.
        if cleaned.get("remove_photo") and self.files.get("photo"):
            self.add_error(
                "remove_photo", "Keep the new photo, or tick this to remove the current one."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("remove_photo"):
            instance.photo = None
        if commit:
            instance.save()
        return instance


class TenantCreateForm(StyledForm):
    """Staff creates a tenant account; the invitation carries the password."""

    username = forms.CharField(
        max_length=150,
        help_text="Used to sign in. Letters, digits and @/./+/-/_ only.",
    )
    email = forms.EmailField(help_text="The invitation is sent here.")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=32, required=False)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already uses that email address.")
        return email


class TenantRoleForm(StyledModelForm):
    """Role change. Only a superadmin may submit it (enforced in the view)."""

    class Meta:
        model = User
        fields = ["role"]


class InvitationPasswordForm(StyledForm, SetPasswordForm):
    """Set-password form used by the invitation and reset-confirm screens."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})
