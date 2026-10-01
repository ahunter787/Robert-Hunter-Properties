"""Tests for the Phase 0 custom user model and the AUTH_USER_MODEL switch."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_auth_user_model_points_at_accounts():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model()._meta.label == "accounts.User"


def test_username_is_unique(user_model):
    user_model.objects.create_user(username="tenant1", password="pw-for-tests")

    with pytest.raises(IntegrityError), transaction.atomic():
        user_model.objects.create_user(username="tenant1", password="pw-for-tests")


def test_str_prefers_full_name_then_username(user_model):
    plain = user_model(username="plain")
    named = user_model(username="named", first_name="Ada", last_name="Lovelace")

    assert str(plain) == "plain"
    assert str(named) == "Ada Lovelace"


def test_created_user_can_authenticate(user_model):
    user_model.objects.create_user(username="tenant2", password="correct-horse-battery")

    assert user_model.objects.get(username="tenant2").check_password("correct-horse-battery")


def test_password_is_hashed(user_model):
    user = user_model.objects.create_user(username="tenant3", password="correct-horse-battery")

    # Hasher-agnostic: Django's default hasher may change between releases.
    assert user.password != "correct-horse-battery"
    assert "correct-horse-battery" not in user.password
    assert user.check_password("correct-horse-battery")


def test_email_validator_rejects_nonsense(user_model):
    user = user_model(username="tenant4", email="not-an-email")

    with pytest.raises(ValidationError):
        user.full_clean()


def test_superuser_flags(user_model):
    admin = user_model.objects.create_superuser(username="root", password="pw-for-tests")

    assert admin.is_staff and admin.is_superuser and admin.is_active
