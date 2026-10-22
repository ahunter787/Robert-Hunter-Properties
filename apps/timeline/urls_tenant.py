from django.urls import path

from . import views

app_name = "tenant_timeline"
urlpatterns = [
    path("", views.tenant_timeline, name="timeline"),
]
