"""Shared pytest fixtures for the RHP test suite."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


@pytest.fixture
def client() -> Client:
    """A Django test client (also provided by pytest-django, aliased for clarity)."""
    return Client()


@pytest.fixture
def user_model():
    """The active user model, so tests do not hardcode a class import."""
    return get_user_model()
