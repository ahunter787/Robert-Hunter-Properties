from django.urls import path

from . import views

app_name = "maintenance"
urlpatterns = [
    path("", views.index, name="list"),
    path("new/", views.create, name="create"),
    path("units/", views.units, name="units"),
    path("vendors/", views.vendors, name="vendors"),
    path("vendors/<int:pk>/", views.vendors, name="vendor-edit"),
    path("notifications/<int:pk>/retry/", views.retry, name="retry"),
    path("attachments/<uuid:public_id>/", views.download, name="download"),
    path("attachments/<uuid:public_id>/remove/", views.remove, name="remove"),
    path("<uuid:public_id>/", views.detail, name="detail"),
    path(
        "<uuid:public_id>/updates/<int:pk>/<slug:operation>/",
        views.update_action,
        name="update-action",
    ),
    path("<uuid:public_id>/costs/<int:pk>/recharge/", views.recharge, name="recharge"),
    path("<uuid:public_id>/<slug:action>/", views.action, name="action"),
]
