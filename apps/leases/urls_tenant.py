"""The tenant's own lease area, mounted at ``/lease/``.

Namespaced ``tenancy`` (not ``leases``, which belongs to the staff screens). This
is the first tenant-facing destination after the account page, and later phases
add their own tenant namespaces beside it: ``payments``, ``maintenance``,
``documents``, ``announcements``.
"""

from django.urls import path

from apps.leases import views

app_name = "tenancy"

urlpatterns = [
    path("", views.TenantLeaseView.as_view(), name="lease"),
    path("document/", views.TenantLeaseDocumentView.as_view(), name="document"),
]
