"""Production settings.

Every value that production depends on is either required from the environment
(a missing secret or host list aborts the boot) or deliberately hardened here.
Nothing in this module may be relaxed to make a deployment "just work".
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# Required, with no fallback: an unset or placeholder secret must stop the boot.
SECRET_KEY = env("DJANGO_SECRET_KEY")
# Whitespace-only entries are dropped: a stray space must not count as a host.
ALLOWED_HOSTS = [
    host.strip() for host in env.list("DJANGO_ALLOWED_HOSTS", default=[]) if host.strip()
]
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS is empty: set the hostname(s) this deployment answers on."
    )

_PLACEHOLDER_SECRETS = {"", "change-me", "insecure-development-only-key"}
if SECRET_KEY in _PLACEHOLDER_SECRETS:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is still a placeholder. Generate one with: "
        'python3 -c "import secrets; print(secrets.token_urlsafe(64))"'
    )

# --- HTTPS topology -------------------------------------------------------
# Caddy terminates TLS and forwards over plain HTTP, so the forwarded-proto
# header is what tells Django the original request was secure.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env.bool("DJANGO_SECURE_PROXY_SSL_HEADER", default=False)
    else None
)

if SECURE_SSL_REDIRECT and SECURE_PROXY_SSL_HEADER is None:
    raise ImproperlyConfigured(
        "SECURE_SSL_REDIRECT is enabled but SECURE_PROXY_SSL_HEADER is unset: Django would "
        "ignore the proxy's scheme header and redirect every request forever. Set "
        "DJANGO_SECURE_PROXY_SSL_HEADER=1 when TLS terminates in front of the app, or "
        "DJANGO_SECURE_SSL_REDIRECT=0 for an intentionally plain-HTTP deployment."
    )

HTTPS_ONLY = SECURE_SSL_REDIRECT

SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_SECURE = HTTPS_ONLY
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=60 * 60 * 12)  # 12 hours

SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000) if HTTPS_ONLY else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS_ONLY
SECURE_HSTS_PRELOAD = HTTPS_ONLY
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Email ----------------------------------------------------------------
# Console email is a development default. It is not unsafe, just nonfunctional,
# so it is a loud warning rather than a failed boot: Phase 1 sends invitations
# and password resets, which is when SMTP configuration becomes mandatory.
# Selecting SMTP without complete credentials, on the other hand, is a
# configuration mistake and aborts the boot.
MAILER_BACKEND = MAILERS["default"]["BACKEND"]  # noqa: F405
MAILER_OPTIONS = MAILERS["default"].get("OPTIONS", {})  # noqa: F405

if MAILER_BACKEND == EMAIL_BACKEND_CONSOLE:  # noqa: F405
    import logging

    logging.getLogger("apps.startup").warning(
        "DJANGO_EMAIL_BACKEND is the console backend: RHP cannot deliver real email yet. "
        "Configure SMTP before Phase 1 sends invitations or password resets."
    )
elif MAILER_BACKEND == EMAIL_BACKEND_SMTP:  # noqa: F405
    _missing_mail_settings = [
        name
        for name, value in (
            ("DJANGO_EMAIL_HOST", MAILER_OPTIONS.get("host")),
            ("DJANGO_EMAIL_HOST_USER", MAILER_OPTIONS.get("username")),
            ("DJANGO_EMAIL_HOST_PASSWORD", MAILER_OPTIONS.get("password")),
        )
        if not value
    ]
    if _missing_mail_settings:
        raise ImproperlyConfigured(
            "SMTP email is configured but these settings are empty: "
            f"{', '.join(_missing_mail_settings)}. Set them, or use the console backend."
        )
