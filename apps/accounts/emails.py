"""Outgoing email for RHP identity flows.

Mail is configured through ``settings.MAILERS`` (Django 6.1); production refuses
to boot with SMTP selected but incomplete, so a deployment cannot silently print
invitations instead of sending them without saying so.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.tokens import invitation_token_generator

logger = logging.getLogger("apps.accounts")


def invitation_path(user) -> str:
    """Site-relative invitation link for ``user``."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = invitation_token_generator.make_token(user)
    return reverse("accounts:invite", kwargs={"uidb64": uid, "token": token})


def invitation_url(user, base_url: str) -> str:
    """Absolute invitation link, e.g. ``https://portal.example.com/account/invite/...``."""
    return f"{base_url.rstrip('/')}{invitation_path(user)}"


def is_console_backend() -> bool:
    """True when mail is only printed to the log (the development default)."""
    return settings.MAILERS["default"]["BACKEND"].endswith("console.EmailBackend")


def send_invitation(user, base_url: str) -> bool:
    """Email the set-password link.

    Returns ``True`` when a real backend handled it, ``False`` when the message
    only reached the console backend - callers surface that to staff so nobody
    believes an invitation was delivered when it was not.
    """
    url = invitation_url(user, base_url)
    subject = render_to_string("account/email/invitation_subject.txt", {"user": user}).strip()
    body = render_to_string(
        "account/email/invitation_body.txt",
        {
            "user": user,
            "invitation_url": url,
            "timeout_days": settings.PASSWORD_RESET_TIMEOUT // 86400,
        },
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])

    if is_console_backend():
        logger.warning(
            "invitation for user=%s went to the console backend (no email delivered): %s",
            user.pk,
            url,
        )
        return False

    logger.info("invitation sent user=%s", user.pk)
    return True
