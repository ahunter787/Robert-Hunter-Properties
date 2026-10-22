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
    path("quick-replies/", views.quick_reply_list, name="quick-replies"),
    path("quick-replies/new/", views.quick_reply_edit, name="quick-reply-new"),
    path("quick-replies/<int:pk>/edit/", views.quick_reply_edit, name="quick-reply-edit"),
    path(
        "quick-replies/<int:pk>/toggle/",
        views.quick_reply_toggle,
        name="quick-reply-toggle",
    ),
    path(
        "messages/<uuid:public_id>/archive/",
        views.conversation_archive,
        name="conversation-archive",
    ),
    path(
        "messages/<uuid:public_id>/mute/",
        views.conversation_mute,
        name="conversation-mute",
    ),
    path(
        "messages/<uuid:public_id>/note/",
        views.conversation_note,
        name="conversation-note",
    ),
    path(
        "messages/<uuid:public_id>/export.<str:fmt>",
        views.conversation_export,
        name="conversation-export",
    ),
    path("deliveries/", views.delivery_list, name="deliveries"),
    path("deliveries/<int:pk>/retry/", views.retry, name="retry"),
]
