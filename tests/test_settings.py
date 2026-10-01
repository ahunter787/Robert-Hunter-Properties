"""Tests that guard the development/production settings split.

Production settings are exercised in a subprocess: several of them exist to abort
the boot, which cannot be observed by importing the module into the already
configured test process. The test runner also rewrites a few settings of its own
accord (``DEBUG``, the default mailer), so those are asserted through a subprocess
import of the settings module rather than from live settings.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent

VALID_PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "unit-test-secret-key-that-is-long-enough-to-be-realistic",
    "DJANGO_ALLOWED_HOSTS": "rhp.example.com",
    "DJANGO_SECURE_PROXY_SSL_HEADER": "1",
    "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "DJANGO_EMAIL_HOST": "smtp.example.com",
    "DJANGO_EMAIL_HOST_USER": "rhp@example.com",
    "DJANGO_EMAIL_HOST_PASSWORD": "unit-test-smtp-password",
}

BOOT = "import django; django.setup()"


def run_settings(
    settings_module: str, code: str = BOOT, **overrides
) -> subprocess.CompletedProcess:
    """Import Django with the given settings module under a controlled environment."""
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": settings_module, **overrides}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def boot_production(**overrides) -> subprocess.CompletedProcess:
    return run_settings("config.settings.production", **{**VALID_PRODUCTION_ENV, **overrides})


# --- The test process itself ------------------------------------------------


def test_test_process_uses_development_settings():
    assert settings.SETTINGS_MODULE == "config.settings.development"
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_email_is_configured_through_mailers():
    # Django 7.0 removes the EMAIL_* settings; MAILERS is the supported form.
    assert "default" in settings.MAILERS
    assert settings.MAILERS["default"]["BACKEND"]

    deprecated = (
        "EMAIL_BACKEND",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
    )
    for name in deprecated:
        assert not settings.is_overridden(name), f"{name} is deprecated - configure MAILERS"


def test_env_file_is_gitignored():
    # Secrets live in .env; if it were ever tracked, a key would reach GitHub.
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )

    assert result.returncode == 0, ".env must be ignored by git"


# --- Development settings ---------------------------------------------------


def test_development_settings_enable_debug():
    result = run_settings(
        "config.settings.development",
        "import django; django.setup()\nfrom django.conf import settings\nprint(settings.DEBUG)",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


# --- Production settings ----------------------------------------------------


def test_production_requires_a_secret_key():
    result = boot_production(DJANGO_SECRET_KEY="")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


@pytest.mark.parametrize("placeholder", ["change-me", "insecure-development-only-key"])
def test_production_rejects_placeholder_secrets(placeholder):
    result = boot_production(DJANGO_SECRET_KEY=placeholder)

    assert result.returncode != 0
    assert "placeholder" in result.stderr


@pytest.mark.parametrize("hosts", ["", " "])
def test_production_requires_allowed_hosts(hosts):
    result = boot_production(DJANGO_ALLOWED_HOSTS=hosts)

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_production_refuses_ssl_redirect_without_proxy_header():
    result = boot_production(
        DJANGO_SECURE_SSL_REDIRECT="1",
        DJANGO_SECURE_PROXY_SSL_HEADER="0",
    )

    assert result.returncode != 0
    assert "SECURE_PROXY_SSL_HEADER" in result.stderr


def test_production_refuses_incomplete_smtp_configuration():
    result = boot_production(DJANGO_EMAIL_HOST="")

    assert result.returncode != 0
    assert "DJANGO_EMAIL_HOST" in result.stderr


def test_production_hardens_cookies_and_transport():
    result = run_settings(
        "config.settings.production",
        "import django; django.setup()\n"
        "from django.conf import settings\n"
        "print(settings.DEBUG, settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE,"
        " settings.SECURE_SSL_REDIRECT, settings.SECURE_HSTS_SECONDS > 0)",
        **VALID_PRODUCTION_ENV,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False True True True True"


def test_production_supports_a_plain_http_deployment_explicitly():
    plain_http = {
        **VALID_PRODUCTION_ENV,
        "DJANGO_SECURE_SSL_REDIRECT": "0",
        "DJANGO_SECURE_PROXY_SSL_HEADER": "0",
    }
    result = run_settings(
        "config.settings.production",
        "import django; django.setup()\n"
        "from django.conf import settings\n"
        "print(settings.SECURE_SSL_REDIRECT, settings.SESSION_COOKIE_SECURE,"
        " settings.SECURE_HSTS_SECONDS)",
        **plain_http,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False 0"


def test_production_boots_with_complete_configuration():
    result = boot_production()

    assert result.returncode == 0, result.stderr
