from django.urls import path

from . import views

app_name = "tenant_communications"
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.new, name="new"),
    path("messages/<uuid:public_id>/", views.conversation, name="conversation"),
    path("messages/<uuid:public_id>/updates/", views.updates, name="updates"),
    path("messages/<uuid:public_id>/read/", views.read, name="read"),
    path("files/<uuid:public_id>/", views.attachment, name="attachment"),
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/<uuid:public_id>/", views.announcement, name="announcement"),
    path("announcements/<uuid:public_id>/contact/", views.followup, name="followup"),
]
