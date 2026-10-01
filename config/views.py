"""Project-level views: the public landing page and the health probe."""

import logging

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

logger = logging.getLogger("apps.health")


def home(request: HttpRequest) -> HttpResponse:
    """Render the (currently public) RHP landing page."""
    return render(request, "pages/home.html")


def healthz(request: HttpRequest) -> JsonResponse:
    """Readiness probe: 200 only when the process can reach PostgreSQL.

    Container healthchecks and uptime monitoring depend on this endpoint, so it
    must stay unauthenticated, cheap, and free of sensitive detail.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - any database failure means "not ready"
        logger.exception("health check failed: database unreachable")
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
