"""No database, credentials, live routes or operational middleware in the prototype."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRET_KEY = secrets.token_urlsafe(48)
DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
ROOT_URLCONF = "tools.design_prototype.urls"
CSRF_FAILURE_VIEW = "tools.design_prototype.views.csrf_failure"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "apps.accounts",
    "apps.properties",
    "apps.leases",
    "apps.ledger",
    "apps.audit",
    "apps.documents",
    "apps.responsibilities",
    "apps.maintenance",
]
AUTH_USER_MODEL = "accounts.User"
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
MAILERS = {"default": {"BACKEND": "tools.design_prototype.settings.DisabledMail"}}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_COOKIE_NAME = "rhp_design_review"
CSRF_COOKIE_NAME = "rhp_design_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
MIDDLEWARE = [
    "tools.design_prototype.views.IsolationHeaders",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ROOT / "templates"],
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
USE_TZ = True
TIME_ZONE = "America/Los_Angeles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 32768
FILE_UPLOAD_MAX_MEMORY_SIZE = 0


class DisabledMail:
    def __init__(self, **kwargs):
        pass

    def send_messages(self, messages):
        raise RuntimeError("The design prototype cannot send email.")
