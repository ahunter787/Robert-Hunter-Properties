"""RHP URL configuration.

Phase 0 exposes three surfaces only: the landing page, the health probe, and
the Django admin (used to create the first superuser).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from config import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Development convenience only. Tenant documents must never be reachable by
    # guessing a media URL: production serves media through permission-checked
    # views (Phase 6), never through the web server or the proxy.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
