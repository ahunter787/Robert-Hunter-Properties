"""Opt-in Phase 8 review against a disposable test database and isolated cookies."""

import os

import pytest

from apps.communications import services
from tests.factories import make_lease, make_manager, make_property, make_tenant, make_unit


class QAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection

        response = self.get_response(request)
        if os.environ.get("RHP_COMM_QA") == "noscript":
            response["Content-Security-Policy"] = "script-src 'none'"
        connection.close()
        return response


@pytest.mark.skipif(not os.environ.get("RHP_COMM_QA"), reason="Opt-in communications browser QA")
@pytest.mark.django_db(transaction=True)
def test_disposable_communications(live_server, settings):
    settings.SESSION_COOKIE_NAME = "rhp_communications_qa_session"
    settings.CSRF_COOKIE_NAME = "rhp_communications_qa_csrf"
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    settings.MIDDLEWARE = ["tests.test_communications_browser.QAMiddleware", *settings.MIDDLEWARE]
    live_server.thread.httpd.get_app().application.application.load_middleware()
    manager = make_manager(username="communications-manager", email="manager@example.test")
    tenant = make_tenant(
        username="communications-tenant",
        first_name="Alex",
        last_name="Example",
        email="alex@example.test",
    )
    other = make_tenant(username="communications-cotenant", first_name="Blair", last_name="Example")
    property = make_property(name="Alder Court", street="100 Example Avenue")
    lease = make_lease(make_unit(property, identifier="Studio A"), tenants=[tenant, other])
    review, _ = services.review_conversation(
        actor=tenant, lease=lease, subject="Parking question", visibility="PRIVATE"
    )
    from uuid import uuid4

    message = services.start_conversation(
        actor=tenant,
        review=review,
        body="Where may guests park?",
        files=[],
        token=uuid4(),
        portal_base=live_server.url,
    )
    notice = services.save_draft(
        actor=manager,
        title="Water service notice",
        body="Synthetic review: water service on Tuesday.",
        important=True,
        expires_at=None,
        properties=[property],
    )
    review, _ = services.review_announcement(
        notice, actor=manager, title=notice.title, body=notice.body, important=True, expires_at=None
    )
    services.publish_announcement(actor=manager, review=review, portal_base=live_server.url)
    input(
        f"\nPhase 8 QA: {live_server.url}/account/login/\n"
        "communications-manager / communications-tenant / communications-cotenant\n"
        "Password: unit-test-password-41\n"
        f"Conversation: /manage/communications/messages/{message.conversation.public_id}/\n"
        "Enter to tear down disposable records.\n"
    )
    assert message.conversation.participants.count() == 1
