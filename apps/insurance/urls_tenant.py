from django.urls import path

from . import views

app_name = "tenant_insurance"
urlpatterns = [
    path("", views.tenant_insurance, name="insurance"),
    path("proof/<int:pk>/", views.proof_document, name="proof-document"),
]
