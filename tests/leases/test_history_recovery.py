"""A missing billing start date must not require recreating existing financial history."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import history_recovery
from apps.leases.models import LeaseAccountStatus, LeaseStatus
from apps.ledger import services
from tests.factories import (
    make_charge,
    make_lease,
    make_maintenance,
    make_manager,
    make_payment,
    make_tenant,
)

pytestmark = pytest.mark.django_db


def existing_account():
    today = timezone.localdate()
    lease = make_lease(
        start_date=today - dt.timedelta(days=80),
        end_date=today + dt.timedelta(days=365),
        billing_start_date=None,
    )
    make_charge(lease, amount=Decimal("1000"), due_date=today - dt.timedelta(days=20))
    make_payment(lease, amount=Decimal("160"))
    return lease


def review(lease, manager):
    return history_recovery.prepare(
        lease,
        billing_start_date=lease.start_date,
        reason="Existing history checked against records",
        actor=manager,
    )


def test_review_back_and_cancel_never_write_and_confirm_keeps_every_entry(client):
    manager = make_manager()
    lease = existing_account()
    url = reverse("leases:onboard", args=[lease.pk])
    charges = list(lease.charges.values())
    payments = list(lease.payments.values())
    balance = services.build_ledger(lease).balance_due
    before = AuditEvent.objects.count()
    client.force_login(manager)
    page = client.get(url)
    assert b"Keep existing account history" in page.content
    assert b"Received before RHP" not in page.content
    assert b"Opening balance</label>" not in page.content
    form_data = {
        "history_recovery": "1",
        "action": "review",
        "billing_start_date": lease.start_date.isoformat(),
        "reason": "Existing history checked against records",
    }
    response = client.post(url, form_data)
    assert response.context["review"] is not None
    assert b"Confirm date and keep history" in response.content
    assert b"no charges" in response.content.lower()
    token = response.context["review"]["token"]
    back = client.post(url, {**form_data, "action": "edit"})
    assert back.context["review"] is None
    assert back.context["form"]["reason"].value() == form_data["reason"]
    lease.refresh_from_db()
    assert lease.billing_start_date is None
    assert AuditEvent.objects.count() == before
    response = client.post(
        url, {"history_recovery": "1", "action": "confirm", "review_token": token}
    )
    assert response.status_code == 302
    lease.refresh_from_db()
    assert lease.billing_start_date == lease.start_date
    assert not lease.needs_onboarding
    assert services.charge_refusal(lease) is None
    assert list(lease.charges.values()) == charges
    assert list(lease.payments.values()) == payments
    assert services.build_ledger(lease).balance_due == balance == Decimal("840")
    assert not lease.has_onboarding, "Do not invent a history/position record or historical receipt"
    event = AuditEvent.objects.get(action=AuditAction.LEASE_ONBOARDED, lease=lease)
    assert event.actor == manager
    assert event.metadata["workflow"] == "keep_existing_history"
    assert event.metadata["reason"] == form_data["reason"]
    assert AuditEvent.objects.count() == before + 1
    client.post(url, {"history_recovery": "1", "action": "confirm", "review_token": token})
    assert AuditEvent.objects.count() == before + 1


@pytest.mark.parametrize("change", ["charge", "payment", "terms", "closed", "replay"])
def test_stale_or_replayed_reviews_do_not_change_history(change):
    lease = existing_account()
    manager = make_manager()
    token = review(lease, manager)["token"]
    if change == "charge":
        make_charge(lease, amount=Decimal("1"), due_date=timezone.localdate())
    elif change == "payment":
        make_payment(lease, amount=Decimal("1"))
    elif change == "terms":
        lease.end_date += dt.timedelta(days=1)
        lease.save(update_fields=["end_date", "updated_at"])
    elif change == "closed":
        lease.status = LeaseStatus.ENDED
        lease.account_status = LeaseAccountStatus.SETTLED
        lease.settled_at = timezone.now()
        lease.save(update_fields=["status", "account_status", "settled_at", "updated_at"])
    else:
        history_recovery.confirm(lease.pk, token=token, actor=manager)
    before = AuditEvent.objects.count()
    with pytest.raises(ValidationError):
        history_recovery.confirm(lease.pk, token=token, actor=manager)
    lease.refresh_from_db()
    if change != "replay":
        assert lease.billing_start_date is None
    assert AuditEvent.objects.count() == before


def test_forged_expired_wrong_actor_and_wrong_lease_tokens_are_rejected(monkeypatch, client):
    lease = existing_account()
    manager = make_manager()
    other = make_manager(username="other-manager")
    token = review(lease, manager)["token"]
    for selected, actor, selected_token in (
        (lease.pk, other, token),
        (lease.pk + 1, manager, token),
        (lease.pk, manager, token + "tampered"),
    ):
        with pytest.raises(ValidationError):
            history_recovery.confirm(selected, token=selected_token, actor=actor)
    with monkeypatch.context() as patch:
        patch.setattr(signing.TimestampSigner, "timestamp", lambda self: "1")
        expired = review(lease, manager)["token"]
    with pytest.raises(ValidationError, match="expired"):
        history_recovery.confirm(lease.pk, token=expired, actor=manager)
    client.force_login(manager)
    response = client.post(
        reverse("leases:onboard", args=[lease.pk]),
        {
            "history_recovery": "1",
            "action": "confirm",
            "review_token": expired,
        },
    )
    assert response.status_code == 200 and b"review expired" in response.content
    lease.refresh_from_db()
    assert lease.billing_start_date is None


@pytest.mark.parametrize("factory", [make_tenant, make_maintenance])
def test_recovery_is_manager_only_at_view_and_service(client, factory):
    lease = existing_account()
    user = factory()
    client.force_login(user)
    url = reverse("leases:onboard", args=[lease.pk])
    assert client.get(url).status_code == 403
    assert client.post(url, {"action": "confirm"}).status_code == 403
    with pytest.raises(PermissionDenied):
        review(lease, user)


def test_validation_no_charges_and_audit_failure_leave_billing_start_untouched(monkeypatch):
    lease = existing_account()
    manager = make_manager()
    with pytest.raises(ValidationError):
        history_recovery.prepare(
            lease,
            billing_start_date=lease.start_date - dt.timedelta(days=1),
            reason="Checked",
            actor=manager,
        )
    with pytest.raises(ValidationError):
        history_recovery.prepare(
            lease, billing_start_date=lease.start_date, reason=" ", actor=manager
        )
    token = review(lease, manager)["token"]

    def refuse(*args, **kwargs):
        raise ValidationError("Audit failure")

    monkeypatch.setattr(history_recovery, "record", refuse)
    with pytest.raises(ValidationError, match="Audit failure"):
        history_recovery.confirm(lease.pk, token=token, actor=manager)
    lease.refresh_from_db()
    assert lease.billing_start_date is None
    empty = make_lease(start_date=lease.start_date, billing_start_date=None)
    with pytest.raises(ValidationError):
        review(empty, manager)
