from django.urls import path

from . import views

app_name = "tenant_maintenance"
urlpatterns = [
    path("", views.index, name="list"),
    path("new/", views.create, name="create"),
    path("attachments/<uuid:public_id>/", views.download, name="download"),
    path("<uuid:public_id>/", views.detail, name="detail"),
    path("<uuid:public_id>/<slug:action>/", views.action, name="action"),
]
