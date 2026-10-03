"""Settings shared by every RHP environment.

Environment-specific overrides live in ``development.py`` and ``production.py``.
Nothing in this file may hardcode a credential: everything comes from the
process environment, optionally seeded from a gitignored ``.env`` file.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Real environment variables always win; .env is only a developer convenience.
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -----------------------------------------------------------------
# The base settings are development-shaped: production.py makes the secret and
# the host list mandatory rather than defaulted.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-development-only-key")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # RHP domain apps are added one per phase (see docs/roadmap.md).
    # `accounts` exists in Phase 0 only to fix AUTH_USER_MODEL early (ADR-002).
    "apps.accounts",
    "apps.properties",
    "apps.leases",
    "apps.ledger",
    "apps.responsibilities",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "libraries": {
                # apps/common is a plain package rather than an installed app, so
                # its shared template filters are registered by path.
                "rhp_format": "apps.common.templatetags.rhp_format",
            },
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database -------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="rhp"),
        "USER": env("POSTGRES_USER", default="rhp"),
        "PASSWORD": env("POSTGRES_PASSWORD", default=""),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {"connect_timeout": 5},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# --- Static and media -----------------------------------------------------
# Static assets are public build output. Media is user data and MUST be served
# through permission-checked views (Phase 6) — never directly by the proxy.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media"))

# --- Portfolio media and maps ---------------------------------------------
# Maximum banner photo size in megabytes; the property form enforces it.
RHP_MAX_UPLOAD_MB = env.int("RHP_MAX_UPLOAD_MB", default=5)
# Expand shortened Google Maps links (maps.app.goo.gl/...) with one outbound
# request to Google when a pin is saved. Every other link shape is parsed offline.
# Turn this off on a host without outbound network — staff can always paste the
# coordinates or the full link instead.
RHP_RESOLVE_MAP_SHORT_LINKS = env.bool("RHP_RESOLVE_MAP_SHORT_LINKS", default=True)
# Optional. When set, the official Google Maps Embed API is used for the map on
# a property page; otherwise the keyless embed is used. RHP never calls Google
# from the server — the browser loads the map.
GOOGLE_MAPS_EMBED_API_KEY = env("GOOGLE_MAPS_EMBED_API_KEY", default="")

# --- The rent ledger ------------------------------------------------------
# How far beyond the current month "create charges" reaches, and how much
# activity the lease pages show. Charging ahead is bounded by the lease's own end
# date, and the same month is never charged twice.
RHP_CHARGE_HORIZON_MONTHS = env.int("RHP_CHARGE_HORIZON_MONTHS", default=1)
RHP_LEDGER_ACTIVITY_LIMIT = env.int("RHP_LEDGER_ACTIVITY_LIMIT", default=5)

# --- Authentication -------------------------------------------------------
LOGIN_URL = "/account/login/"
# Name of the role-aware redirect view: staff land on the management area,
# tenants on their account page.
LOGIN_REDIRECT_URL = "accounts:home"
LOGOUT_REDIRECT_URL = "/"

# Invitation and password-reset links share this window: Django hardcodes
# PASSWORD_RESET_TIMEOUT inside the token check, so a second, longer window for
# invitations would mean duplicating security-sensitive verification logic.
PASSWORD_RESET_TIMEOUT = env.int("RHP_LINK_TIMEOUT_DAYS", default=7) * 24 * 60 * 60

# Login throttling (docs/security.md): this many failures inside the window
# locks the account/address out for the lockout period.
RHP_LOGIN_MAX_ATTEMPTS = env.int("RHP_LOGIN_MAX_ATTEMPTS", default=5)
RHP_LOGIN_WINDOW_MINUTES = env.int("RHP_LOGIN_WINDOW_MINUTES", default=15)
RHP_LOGIN_LOCKOUT_MINUTES = env.int("RHP_LOGIN_LOCKOUT_MINUTES", default=15)
# Honor X-Forwarded-For when deciding a client address. Enable only when a
# trusted proxy sets it (the production Compose stack does).
RHP_TRUST_PROXY_HEADERS = env.bool("RHP_TRUST_PROXY_HEADERS", default=False)

# --- Email ----------------------------------------------------------------
# Django 6.1 configures outgoing mail through MAILERS. The older EMAIL_* settings
# are deprecated (removed in Django 7.0) and Django rejects them outright when
# MAILERS is defined, so MAILERS is the only supported form here.
EMAIL_BACKEND_CONSOLE = "django.core.mail.backends.console.EmailBackend"
EMAIL_BACKEND_SMTP = "django.core.mail.backends.smtp.EmailBackend"

_email_backend = env("DJANGO_EMAIL_BACKEND", default=EMAIL_BACKEND_CONSOLE)
_email_options: dict[str, object] = {}
if _email_backend == EMAIL_BACKEND_SMTP:
    # SMTP backends reject unknown OPTIONS, so only these keys are ever passed.
    _email_options = {
        "host": env("DJANGO_EMAIL_HOST", default=""),
        "port": env.int("DJANGO_EMAIL_PORT", default=587),
        "username": env("DJANGO_EMAIL_HOST_USER", default=""),
        "password": env("DJANGO_EMAIL_HOST_PASSWORD", default=""),
        "use_tls": env.bool("DJANGO_EMAIL_USE_TLS", default=True),
    }

MAILERS = {"default": {"BACKEND": _email_backend, "OPTIONS": _email_options}}

DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="RHP <no-reply@localhost>")

# --- Logging --------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
