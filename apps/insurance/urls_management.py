from django.urls import path

from . import views

app_name = "insurance"
urlpatterns = [
    path("", views.staff_list, name="staff-list"),
    path("<int:pk>/", views.staff_detail, name="staff-detail"),
    path("proof/<int:pk>/", views.proof_document, name="proof-document"),
]
