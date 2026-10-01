"""Login throttling: the failure budget, the window, and the support escape hatch."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import LoginAttempt
from apps.accounts.throttle import LoginThrottle, client_ip
from tests.factories import DEFAULT_PASSWORD, make_admin, make_tenant

pytestmark = pytest.mark.django_db


def fail_login(client, username, times, password="wrong-password"):
    for _ in range(times):
        response = client.post(
            reverse("accounts:login"), {"username": username, "password": password}
        )
    return response


def test_account_locks_after_the_configured_failures(client, settings):
    settings.RHP_LOGIN_MAX_ATTEMPTS = 3
    make_tenant(username="locked-tenant")

    fail_login(client, "locked-tenant", 3)

    # Even the correct password is refused while locked, and the message is generic.
    response = client.post(
        reverse("accounts:login"),
        {"username": "locked-tenant", "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    assert "Too many unsuccessful sign-in attempts" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_lockout_also_covers_the_client_address(client, settings):
    settings.RHP_LOGIN_MAX_ATTEMPTS = 2
    make_tenant(username="ip-throttled")

    fail_login(client, "ip-throttled", 2)

    # A different username from the same address is refused too.
    response = client.post(
        reverse("accounts:login"), {"username": "somebody-else", "password": "wrong"}
    )

    assert "Too many unsuccessful sign-in attempts" in response.content.decode()


def test_lockout_expires_with_the_window(client, settings):
    settings.RHP_LOGIN_MAX_ATTEMPTS = 2
    settings.RHP_LOGIN_LOCKOUT_MINUTES = 15
    make_tenant(username="windowed")

    fail_login(client, "windowed", 2)
    # Move the recorded failures outside the window.
    LoginAttempt.objects.update(created_at=timezone.now() - dt.timedelta(minutes=30))

    response = client.post(
        reverse("accounts:login"),
        {"username": "windowed", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 302
    assert "_auth_user_id" in client.session


def test_throttle_state_reports_remaining_time(settings):
    settings.RHP_LOGIN_MAX_ATTEMPTS = 1
    settings.RHP_LOGIN_LOCKOUT_MINUTES = 10
    throttle = LoginThrottle()

    throttle.record_failure("someone", "10.0.0.1")
    state = throttle.state("someone", "10.0.0.1")

    assert state.locked is True
    assert 1 <= state.retry_after_minutes <= 10


def test_successful_login_resets_the_budget():
    throttle = LoginThrottle()
    throttle.record_failure("reset-me", "10.0.0.2")

    throttle.record_success("reset-me", "10.0.0.2")

    assert throttle.state("reset-me", "10.0.0.2").locked is False
    assert LoginAttempt.objects.filter(username="reset-me", successful=False).count() == 0


def test_usernames_are_matched_case_insensitively():
    throttle = LoginThrottle()
    throttle.record_failure("MixedCase", None)

    assert throttle.state("mixedcase", None).locked is False  # one failure is under budget
    throttle.record_failure("MIXEDCASE", None)
    throttle.record_failure("mixedcase", None)
    throttle.record_failure("mixedCASE", None)
    throttle.record_failure("mixedcase", None)

    assert throttle.state("mixedcase", None).locked is True


def test_reset_login_attempts_command_clears_a_username(capsys):
    throttle = LoginThrottle()
    throttle.record_failure("stuck-user", "10.0.0.3")

    call_command("reset_login_attempts", "stuck-user")
    output = capsys.readouterr().out

    assert "Cleared" in output
    assert LoginAttempt.objects.filter(username="stuck-user").count() == 0


def test_reset_login_attempts_command_can_target_an_address():
    throttle = LoginThrottle()
    throttle.record_failure("user-a", "10.0.0.9")

    call_command("reset_login_attempts", "10.0.0.9", "--ip")

    assert LoginAttempt.objects.filter(ip="10.0.0.9").count() == 0


def test_client_ip_ignores_forwarded_headers_by_default(settings, rf):
    settings.RHP_TRUST_PROXY_HEADERS = False
    request = rf.post("/", REMOTE_ADDR="10.1.1.1", HTTP_X_FORWARDED_FOR="203.0.113.5")

    assert client_ip(request) == "10.1.1.1"


def test_client_ip_honours_forwarded_headers_when_trusted(settings, rf):
    settings.RHP_TRUST_PROXY_HEADERS = True
    request = rf.post("/", REMOTE_ADDR="10.1.1.1", HTTP_X_FORWARDED_FOR="203.0.113.5, 10.1.1.1")

    assert client_ip(request) == "203.0.113.5"


def test_old_attempts_are_pruned(settings):
    throttle = LoginThrottle()
    old = LoginAttempt.objects.create(username="ancient", successful=False)
    LoginAttempt.objects.filter(pk=old.pk).update(created_at=timezone.now() - dt.timedelta(days=2))

    throttle.record_failure("fresh", None)

    assert LoginAttempt.objects.filter(username="ancient").count() == 0


def test_staff_accounts_run_out_of_budget_too(client, settings):
    settings.RHP_LOGIN_MAX_ATTEMPTS = 2
    make_admin(username="throttled-admin")

    fail_login(client, "throttled-admin", 2)
    response = client.post(
        reverse("accounts:login"), {"username": "throttled-admin", "password": DEFAULT_PASSWORD}
    )

    assert "Too many unsuccessful sign-in attempts" in response.content.decode()
