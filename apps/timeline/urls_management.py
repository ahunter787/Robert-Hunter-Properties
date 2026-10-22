from django.urls import path

from . import views

app_name = "timeline"
urlpatterns = [
    path("", views.staff_list, name="list"),
    path("<int:pk>/", views.staff_lease, name="lease"),
]
