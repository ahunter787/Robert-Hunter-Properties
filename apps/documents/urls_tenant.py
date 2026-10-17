"""The tenant's own documents, mounted under ``/lease/``.

Its own namespace (``tenant_documents``) rather than ``tenancy``: two URL modules
cannot share one namespace — the second one's names become unreachable — and the
office's document namespace is ``documents``. Every route resolves through the
tenancy scope, so an id that is not theirs is a 404 rather than a refusal that admits
the document exists (ADR-022).
"""

from django.urls import path

from apps.documents import views

app_name = "tenant_documents"

urlpatterns = [
    path("documents/", views.TenantDocumentListView.as_view(), name="list"),
    path(
        "documents/<int:pk>/download/",
        views.TenantDocumentDownloadView.as_view(),
        name="download",
    ),
]
