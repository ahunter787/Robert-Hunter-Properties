"""Tests for the operational endpoints: the landing page and /healthz."""

import pytest
from django.db import DatabaseError
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_home_renders(client):
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Robert Hunter Properties" in response.content
    assert b"rhp.css" in response.content


def test_healthz_reports_ok_when_database_answers(client, django_assert_num_queries):
    with django_assert_num_queries(1):
        response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_healthz_reports_503_when_database_is_unreachable(client, monkeypatch):
    class BrokenCursor:
        def __enter__(self):
            raise DatabaseError("database is down")

        def __exit__(self, *exc_info):
            return False

    import config.views as views

    monkeypatch.setattr(views.connection, "cursor", lambda: BrokenCursor())

    response = client.get(reverse("healthz"))

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unreachable"}


def test_healthz_requires_no_authentication(client):
    response = client.get("/healthz")

    assert response.status_code == 200


def test_admin_login_is_reachable(client):
    response = client.get("/admin/login/")

    assert response.status_code == 200
