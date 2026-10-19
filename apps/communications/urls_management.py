from django.urls import path

from . import views
from .urls_tenant import urlpatterns as shared

app_name = "communications"
urlpatterns = [
    *shared,
    path("messages/<uuid:public_id>/work/", views.work, name="work"),
    path("announcements/new/", views.draft, name="draft-new"),
    path("announcements/<uuid:public_id>/draft/", views.draft, name="draft"),
    path("announcements/<uuid:public_id>/publish/", views.publish, name="publish"),
    path("announcements/<uuid:public_id>/withdraw/", views.withdraw, name="withdraw"),
    path("deliveries/", views.delivery_list, name="deliveries"),
    path("deliveries/<int:pk>/retry/", views.retry, name="retry"),
]
