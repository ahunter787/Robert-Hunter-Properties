"""Small authorized dashboard projections, independent of financial balances."""

from django.urls import reverse
from django.utils import timezone

from .models import Announcement, Conversation


def communications_summary(user):
    if not user.is_active or not (user.is_tenant or user.is_manager_or_above):
        return None
    from .views import with_unread

    rows = Conversation.objects.visible_to(user).filter(messages__isnull=False).distinct()
    ns = "tenant_communications" if user.is_tenant else "communications"
    now = timezone.now()
    active_notices = sum(
        1
        for notice in Announcement.objects.visible_to(user).filter(
            published_at__isnull=False, withdrawn_at__isnull=True
        )
        if (version := notice.latest) and (not version.expires_at or version.expires_at > now)
    )
    return {
        "unread": with_unread(rows, user).filter(unread=True).count(),
        "needs_reply": rows.filter(state="NEEDS_RHP", frozen_at=None).count(),
        "announcements": active_notices,
        "messages_url": reverse(f"{ns}:index"),
        "announcements_url": reverse(f"{ns}:announcements"),
    }
