"""Password reset: the happy path, expiry, and the no-enumeration rule."""

import pytest
from django.urls import reverse

from tests.factories import make_tenant, password_reset_path_from_email

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "a-brand-new-password-77"


def test_reset_page_renders(client):
    response = client.get(reverse("accounts:password-reset"))

    assert response.status_code == 200
    assert b"reset link" in response.content


def test_known_and_unknown_addresses_are_indistinguishable(client, mailoutbox):
    make_tenant(username="known-address", email="known@example.com")

    known = client.post(reverse("accounts:password-reset"), {"email": "known@example.com"})
    unknown = client.post(reverse("accounts:password-reset"), {"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 302
    assert known["Location"] == unknown["Location"] == reverse("accounts:password-reset-done")
    # Only the real account produced mail; the response revealed nothing.
    assert len(mailoutbox) == 1


def test_done_page_repeats_the_generic_message(client, mailoutbox):
    client.post(reverse("accounts:password-reset"), {"email": "nobody@example.com"})

    body = client.get(reverse("accounts:password-reset-done")).content.decode()

    assert "If an RHP account exists for that address" in body


def test_reset_link_sets_a_new_password(client, mailoutbox):
    tenant = make_tenant(username="reset-me", email="reset@example.com")
    client.post(reverse("accounts:password-reset"), {"email": "reset@example.com"})

    link_path = password_reset_path_from_email(mailoutbox[-1].body)
    redirect = client.get(link_path)
    assert redirect.status_code == 302

    set_password_path = redirect["Location"]
    assert client.get(set_password_path).status_code == 200

    response = client.post(
        set_password_path, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("accounts:password-reset-complete")
    tenant.refresh_from_db()
    assert tenant.check_password(NEW_PASSWORD)


def test_reset_link_cannot_be_reused(client, mailoutbox):
    make_tenant(username="once-only", email="once@example.com")
    client.post(reverse("accounts:password-reset"), {"email": "once@example.com"})
    link_path = password_reset_path_from_email(mailoutbox[-1].body)

    redirect = client.get(link_path)
    set_password_path = redirect["Location"]
    client.post(set_password_path, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})

    second = client.get(link_path, follow=True)

    assert b"no longer works" in second.content


def test_tampered_reset_link_is_rejected(client, mailoutbox):
    make_tenant(username="tampered", email="tampered@example.com")
    client.post(reverse("accounts:password-reset"), {"email": "tampered@example.com"})
    link_path = password_reset_path_from_email(mailoutbox[-1].body)

    tampered = link_path[:-3] + "aaa"
    response = client.get(tampered, follow=True)

    assert b"no longer works" in response.content


def test_reset_confirm_password_must_not_be_too_short(client, mailoutbox):
    make_tenant(username="weak-pass", email="weak@example.com")
    client.post(reverse("accounts:password-reset"), {"email": "weak@example.com"})
    link_path = password_reset_path_from_email(mailoutbox[-1].body)
    set_password_path = client.get(link_path)["Location"]

    response = client.post(set_password_path, {"new_password1": "short", "new_password2": "short"})

    assert response.status_code == 200
    assert b"too short" in response.content
