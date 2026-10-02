"""The tenant's own money, mounted at ``/payments/``.

Namespaced ``payments`` rather than reusing ``ledger``, which belongs to the
staff screens: a tenant-facing route must never share a namespace with the areas
a tenant is refused.
"""

from django.urls import path

from apps.ledger import views

app_name = "payments"

urlpatterns = [
    path("", views.TenantPaymentsView.as_view(), name="home"),
]
