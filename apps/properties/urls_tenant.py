from django.urls import path

from apps.properties.views import TenantLocationPhotoView

app_name = "tenant_portfolio"
urlpatterns = [
    path("location-photo/<slug:kind>/", TenantLocationPhotoView.as_view(), name="photo"),
]
