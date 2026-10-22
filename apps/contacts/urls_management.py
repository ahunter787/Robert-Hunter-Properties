"""People management URLs, mounted under ``/manage/people/``."""

from django.urls import path

from apps.contacts import views

app_name = "contacts"

urlpatterns = [
    path("", views.PersonListView.as_view(), name="person-list"),
    path("new/", views.PersonCreateView.as_view(), name="person-create"),
    path("<int:pk>/", views.PersonDetailView.as_view(), name="person-detail"),
    path("<int:pk>/edit/", views.PersonUpdateView.as_view(), name="person-update"),
    path(
        "<int:pk>/link-account/",
        views.PersonLinkAccountView.as_view(),
        name="person-link-account",
    ),
]
