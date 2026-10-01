"""Forms for RHP identity screens.

Every form inherits :class:`StyledForm` so templates can render ``{{ field }}``
without repeating design-system classes, and so server-side validation messages
stay in one place.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import ValidationError

from apps.accounts.models import TenantProfile, User
from apps.accounts.throttle import LoginThrottle, client_ip


class StyledForm(forms.Form):
    """Applies the RHP design-system classes to all widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "h-4 w-4 rounded border-surface-muted text-primary"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "rhp-field pr-8"
            elif isinstance(widget, forms.Textarea):
                css = "rhp-field min-h-24"
            else:
                css = "rhp-field"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class StyledModelForm(StyledForm, forms.ModelForm):
    """ModelForm variant of :class:`StyledForm`."""


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
