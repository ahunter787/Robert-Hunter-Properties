"""RHP URL configuration.

Three surfaces: the public landing page and health probe, the account area
(sign-in and self-service), and the staff management area. The Django admin
remains available for the back office.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("account/", include("apps.accounts.urls")),
    path("manage/", include("apps.accounts.urls_management")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Development convenience only. Tenant documents must never be reachable by
    # guessing a media URL: production serves media through permission-checked
    # views (Phase 6), never through the web server or the proxy.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
