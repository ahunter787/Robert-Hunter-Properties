"""RHP URL configuration.

Three surfaces: the public landing page and health probe, the account area
(sign-in and self-service), and the staff management area. The Django admin
remains available for the back office.
"""

from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("account/", include("apps.accounts.urls")),
    path("manage/", include("apps.accounts.urls_management")),
    path("manage/", include("apps.properties.urls_management")),
    path("manage/", include("apps.leases.urls_management")),
    path("manage/people/", include("apps.contacts.urls_management")),
    path("manage/", include("apps.responsibilities.urls_management")),
    path("manage/ledger/", include("apps.ledger.urls_management")),
    path("manage/", include("apps.documents.urls_management")),
    path("lease/", include("apps.leases.urls_tenant")),
    path("lease/", include("apps.properties.urls_tenant")),
    path("lease/", include("apps.documents.urls_tenant")),
    path("payments/", include("apps.ledger.urls_tenant")),
    path("maintenance/", include("apps.maintenance.urls_tenant")),
    path("manage/maintenance/", include("apps.maintenance.urls_management")),
    path("communications/", include("apps.communications.urls_tenant")),
    path("manage/communications/", include("apps.communications.urls_management")),
    path("admin/", admin.site.urls),
]

# Private uploads are served only by authorized download views, including in development.
