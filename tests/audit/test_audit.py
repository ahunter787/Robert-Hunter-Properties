"""The audit trail: every change that matters leaves a record.

The events are the reason a balance can be trusted, so their content is asserted,
not merely their existence — actor, action, target and the facts of the change.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import events_for_lease, record
from apps.ledger import services
from apps.ledger.models import Direction, PaymentStatus
from tests.factories import make_admin, make_charge, make_lease, make_payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def test_a_charge_leaves_an_event_naming_the_actor():
    manager = make_admin(username="audit-admin")
    lease = make_lease()

    charge = services.create_charge(
        lease,
        description="Replacement keys",
        amount=Decimal("45.00"),
        due_date=TODAY,
        actor=manager,
    )

    event = AuditEvent.objects.get(action=AuditAction.CHARGE_CREATED)
    assert event.actor == manager
    assert event.object_type == "ledger.Charge"
    assert event.object_id == charge.pk
    assert event.lease == lease
    assert event.metadata["amount"] == "45.00", "money is stored in the event as a string"
    assert event.summary


def test_recording_a_payment_leaves_an_event():
    manager = make_admin(username="audit-admin")
    lease = make_lease()

    services.record_payment(
        lease,
        amount=Decimal("1850.00"),
        payment_date=TODAY,
        method="ACH",
        status=PaymentStatus.CLEARED,
        external_reference="ACH-1",
        actor=manager,
    )

    event = AuditEvent.objects.get(action=AuditAction.PAYMENT_RECORDED)
    assert event.metadata["method"] == "ACH"
    assert event.metadata["status"] == "CLEARED"
    assert event.metadata["external_reference"] == "ACH-1"


def test_clearing_voiding_and_reversing_are_each_recorded():
    manager = make_admin(username="audit-admin")
    lease = make_lease()
    first = make_payment(
        lease, amount=Decimal("100.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )
    second = make_payment(
        lease, amount=Decimal("200.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )
    third = make_payment(lease, amount=Decimal("300.00"), payment_date=TODAY)

    services.clear_payment(first, actor=manager)
    services.void_payment(second, actor=manager, reason="never arrived")
    services.reverse_payment(third, reason="duplicate entry", actor=manager)

    actions = set(AuditEvent.objects.values_list("action", flat=True))
    # The payments themselves were built directly (no service call), so only the
    # three lifecycle actions were recorded — which is the point: the services are
    # what write the trail, and every screen goes through them.
    assert actions == {
        AuditAction.PAYMENT_CLEARED,
        AuditAction.PAYMENT_VOIDED,
        AuditAction.PAYMENT_REVERSED,
    }
    reversed_event = AuditEvent.objects.get(action=AuditAction.PAYMENT_REVERSED)
    assert reversed_event.metadata["reversed_payment"] == str(third.pk)
    assert reversed_event.metadata["reason"] == "duplicate entry"


def test_an_adjustment_is_recorded_with_its_reason():
    manager = make_admin(username="audit-admin")
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)

    services.create_adjustment(
        charge,
        direction=Direction.DECREASE,
        amount=Decimal("25.00"),
        reason="overcharged",
        actor=manager,
    )

    event = AuditEvent.objects.get(action=AuditAction.CHARGE_ADJUSTED)
    assert event.metadata["reason"] == "overcharged"
    assert event.metadata["direction"] == "DECREASE"
    assert event.metadata["adjusts"] == str(charge.pk)


def test_generating_rent_charges_records_one_event_each():
    # Start at the beginning of a month whose due day has arrived, so the test
    # does not depend on which day of the month it happens to run.
    lease = make_lease(start_date=TODAY.replace(day=1), rent_due_day=1)

    services.generate_rent_charges(lease, through=TODAY)

    events = AuditEvent.objects.filter(action=AuditAction.CHARGE_CREATED)
    assert events.count() >= 1
    assert all(event.summary for event in events)


def test_a_command_with_no_actor_still_records_the_change():
    lease = make_lease(start_date=TODAY.replace(day=1), rent_due_day=1)

    services.generate_rent_charges(lease, through=TODAY, actor=None)

    event = AuditEvent.objects.filter(action=AuditAction.CHARGE_CREATED).first()
    assert event is not None
    assert event.actor is None


def test_the_history_of_a_lease_holds_its_own_events():
    mine = make_lease()
    theirs = make_lease()
    services.create_charge(
        mine, description="Mine", amount=Decimal("10.00"), due_date=TODAY, actor=None
    )
    services.create_charge(
        theirs, description="Theirs", amount=Decimal("10.00"), due_date=TODAY, actor=None
    )

    events = list(events_for_lease(mine))

    assert len(events) == 1
    assert events[0].lease == mine


def test_an_event_is_never_edited():
    event = record(None, AuditAction.LEASE_ACTIVATED, summary="something happened")

    event.summary = "rewritten"
    with pytest.raises(ValidationError, match="append-only"):
        event.save()


def test_an_event_is_never_deleted():
    event = record(None, AuditAction.LEASE_ACTIVATED, summary="something happened")

    with pytest.raises(ValidationError, match="never deleted"):
        event.delete()
    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_an_event_survives_the_actor_being_deactivated():
    """Accounts are deactivated, never deleted, so the trail keeps its actor."""
    manager = make_admin(username="audit-admin")
    lease = make_lease()
    services.create_charge(
        lease, description="Keys", amount=Decimal("10.00"), due_date=TODAY, actor=manager
    )

    manager.is_active = False
    manager.save()

    event = AuditEvent.objects.get(action=AuditAction.CHARGE_CREATED)
    event.refresh_from_db()
    assert event.actor == manager


def test_an_actor_that_is_not_a_user_is_stored_as_nobody():
    event = record("not-a-user", AuditAction.PAYMENT_RECORDED, summary="x")

    assert event.actor is None
