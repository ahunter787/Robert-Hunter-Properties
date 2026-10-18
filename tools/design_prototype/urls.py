from django.urls import path

from . import views

urlpatterns = [
    path("assets/<str:name>", views.asset),
    path("allocation/<int:pk>/", views.allocation, name="prototype-allocation"),
    path("allocation/<int:pk>/preview/", views.allocation_preview),
    path("reset/", views.reset),
    path("", views.page),
    path("<str:area>/", views.page),
    path("<str:area>/<int:pk>/", views.page),
]
