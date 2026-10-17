"""Document management URLs, mounted under ``/manage/``."""

from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
    path("documents/", views.DocumentListView.as_view(), name="list"),
    path("documents/upload/", views.DocumentUploadView.as_view(), name="upload"),
    path("documents/<int:pk>/download/", views.DocumentDownloadView.as_view(), name="download"),
    path("documents/<int:pk>/remove/", views.DocumentRemoveView.as_view(), name="remove"),
]
