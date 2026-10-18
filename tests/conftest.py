"""Shared pytest fixtures for the RHP test suite."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings


@pytest.fixture
def client() -> Client:
    """A Django test client (also provided by pytest-django, aliased for clarity)."""
    return Client()


@pytest.fixture
def user_model():
    """The active user model, so tests do not hardcode a class import."""
    return get_user_model()


@pytest.fixture(autouse=True)
def media_root(tmp_path):
    """Point MEDIA_ROOT at a per-test temporary directory.

    Uploads must never land in the repository, no test can leave files behind for
    the next one, and ``override_settings`` is used rather than assigning the
    setting because Django only resets its cached storage backend when the
    ``setting_changed`` signal fires.
    """
    with override_settings(MEDIA_ROOT=tmp_path / "media"):
        yield tmp_path / "media"


@pytest.fixture
def restore_schema(django_db_setup, django_db_blocker):
    """Historical migration tests must not leave later transactional tests on an old schema."""
    yield
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
