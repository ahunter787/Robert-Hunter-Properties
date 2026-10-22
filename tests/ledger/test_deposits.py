"""A security deposit is held money with an outcome, not a lease number (ADR-028 D5).

The bug these tests exist for: any nonzero recorded deposit blocked settlement, pointing at
a move-out workflow that did not exist. Now the register says what is held, and a move-out
outcome — refund, itemised withhold, or an explicit "none collected" — is what lets the
financial account close. A deposit is never AR and never a tenant credit.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.ledger import deposits
from apps.ledger.models import DepositEntry, DepositKind
from tests.factories import make_lease, make_manager, make_tenant
from tests.leases.payloads import lease_post_data

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")


def a_running_lease(**fields):
    fields.setdefault("deposit", Decimal("1000.00"))
    return make_lease(**fields)


def end(lease):
    lease.status = "ENDED"
    lease.ended_on = TODAY
    lease.end_reason = "END_OF_TERM"
    lease.save(update_fields=["status", "ended_on", "end_reason"])
    return lease


def an_ended_lease(**fields):
    return end(a_running_lease(**fields))


def receive(lease, amount="1000.00", **fields):
    return deposits.record(
        lease,
        kind=DepositKind.RECEIVED,
        amount=Decimal(amount),
        date=TODAY,
        method="CHECK",
        **fields,
    )


def release(lease, kind, amount, *, reason="", **fields):
    return deposits.record(
        lease,
        kind=kind,
        amount=Decimal(amount),
        date=TODAY,
        reason=reason,
        **fields,
    )


# --- the register ---------------------------------------------------------


def test_received_money_is_held():
    lease = a_running_lease()
    receive(lease)

    assert deposits.held(lease) == Decimal("1000.00")
    assert deposits.has_received(lease)
    assert deposits.addressed(lease) is False, "held money is not an outcome yet"
    assert "still held" in (deposits.blocker(lease) or "")


def test_a_partial_refund_and_an_itemised_withhold_release_everything():
    lease = a_running_lease()
    receive(lease)
    end(lease)
    release(lease, DepositKind.RETURNED, "600.00")
    release(lease, DepositKind.WITHHELD, "350.00", reason="Cleaning and a broken blind")

    assert deposits.held(lease) == Decimal("50.00"), "the arithmetic is the register's"
    release(lease, DepositKind.RETURNED, "50.00")
    assert deposits.held(lease) == ZERO
    assert deposits.blocker(lease) is None


def test_a_withhold_needs_a_reason():
    lease = a_running_lease()
    receive(lease)
    end(lease)

    with pytest.raises(ValidationError, match="Say what was retained"):
        release(lease, DepositKind.WITHHELD, "100.00")


def test_a_release_cannot_exceed_what_is_held():
    lease = a_running_lease()
    receive(lease, "100.00")
    end(lease)

    with pytest.raises(ValidationError, match="Only 100.00 is held"):
        release(lease, DepositKind.RETURNED, "150.00")


def test_deposit_money_is_recorded_while_running_and_disposed_only_after_ending():
    running = a_running_lease()
    receive(running)
    with pytest.raises(ValidationError, match="when the tenancy ends"):
        release(running, DepositKind.RETURNED, "100.00")

    ended = an_ended_lease()
    with pytest.raises(ValidationError, match="while the tenancy is running"):
        receive(ended)


def test_not_collected_is_an_explicit_outcome_not_inferred():
    lease = an_ended_lease()

    with pytest.raises(ValidationError, match="Say why no deposit"):
        deposits.record(lease, kind=DepositKind.NOT_COLLECTED, amount=ZERO, date=TODAY, reason="")

    deposits.record(
        lease, kind=DepositKind.NOT_COLLECTED, amount=ZERO, date=TODAY, reason="Moved in 2022"
    )
    assert deposits.held(lease) == ZERO
    assert deposits.addressed(lease) is True
    assert deposits.blocker(lease) is None
    assert lease.deposit == Decimal("1000.00"), "the agreed term is still the term"


def test_not_collected_is_refused_when_money_is_recorded():
    lease = a_running_lease()
    receive(lease)
    end(lease)

    with pytest.raises(ValidationError, match="already records deposit money"):
        deposits.record(
            lease,
            kind=DepositKind.NOT_COLLECTED,
            amount=ZERO,
            date=TODAY,
            reason="Nonsense",
        )


def test_entries_are_append_only_and_audited():
    lease = a_running_lease()
    entry = receive(lease)

    with pytest.raises(ValidationError):
        entry.reason = "changed"
        entry.save()
    with pytest.raises(ValidationError):
        entry.delete()
    assert AuditEvent.objects.filter(action=AuditAction.DEPOSIT_CHANGED, lease=lease).count() == 1


def test_a_settled_account_refuses_deposit_entries():
    lease = an_ended_lease(deposit=Decimal("0"))
    lease_services.settle_account(lease)

    with pytest.raises(ValidationError, match="settled"):
        receive(lease)


# --- settlement -----------------------------------------------------------


def test_held_money_blocks_settlement_with_an_actionable_message():
    lease = a_running_lease()
    receive(lease)
    end(lease)

    with pytest.raises(ValidationError, match="is still held"):
        lease_services.settle_account(lease)


def test_an_agreed_deposit_without_an_outcome_blocks_settlement():
    lease = an_ended_lease()

    with pytest.raises(ValidationError, match="no recorded outcome"):
        lease_services.settle_account(lease)


def test_settlement_succeeds_once_the_deposit_is_disposed():
    lease = a_running_lease()
    receive(lease)
    end(lease)
    release(lease, DepositKind.RETURNED, "1000.00")

    lease_services.settle_account(lease)
    lease.refresh_from_db()
    assert lease.account_status == "SETTLED"


def test_settlement_succeeds_when_none_was_collected():
    lease = an_ended_lease()
    deposits.record(
        lease, kind=DepositKind.NOT_COLLECTED, amount=ZERO, date=TODAY, reason="Not collected"
    )

    lease_services.settle_account(lease)
    lease.refresh_from_db()
    assert lease.account_status == "SETTLED"


def test_a_receipt_is_never_mistaken_for_deposit_money():
    """The register does not read payments or the lease term; only its own entries count."""
    lease = a_running_lease(deposit=Decimal("1850.00"))
    from tests.factories import make_payment

    make_payment(lease, amount=Decimal("1850.00"))
    assert deposits.held(lease) == ZERO
    assert deposits.addressed(lease) is False


# --- screens --------------------------------------------------------------


def test_a_manager_records_a_deposit_through_the_plain_form(client):
    lease = a_running_lease()
    client.force_login(make_manager())

    response = client.post(
        reverse("ledger:deposit", args=[lease.pk]),
        {
            "kind": DepositKind.RECEIVED,
            "amount": "1000.00",
            "date": TODAY.isoformat(),
            "method": "CHECK",
            "reference": "Check 118",
            "reason": "",
            "evidence": "",
        },
    )

    assert response.status_code == 302
    assert deposits.held(lease) == Decimal("1000.00")


def test_the_tenant_sees_what_is_held_but_not_as_a_credit(client):
    tenant = make_tenant(username="deposit-tenant")
    lease = a_running_lease(tenants=[tenant])
    receive(lease, "1000.00")
    client.force_login(tenant)

    body = " ".join(strip_tags(client.get(reverse("payments:home")).content.decode()).split())
    assert "$1,000.00" not in body, "a held deposit is not a credit on the statement"
    lease_body = " ".join(strip_tags(client.get(reverse("tenancy:lease")).content.decode()).split())
    assert "$1,000.00 held" in lease_body


def test_a_tenant_cannot_reach_the_deposit_screen(client):
    lease = a_running_lease()
    client.force_login(make_tenant(username="deposit-tenant-2"))

    assert client.get(reverse("ledger:deposit", args=[lease.pk])).status_code == 403


def test_the_agreed_term_cannot_be_edited_below_held_money(client):
    lease = a_running_lease()
    receive(lease, "400.00")
    client.force_login(make_manager())

    data = lease_post_data(lease.unit, lease=lease, deposit="100.00")
    response = client.post(reverse("leases:lease-update", args=[lease.pk]), data)

    assert response.status_code == 200
    lease.refresh_from_db()
    assert lease.deposit == Decimal("1000.00")
    assert "already held for this tenancy" in response.content.decode()


def test_deposit_evidence_is_a_staff_document_on_the_same_tenancy():
    from tests.documents.helpers import make_document

    lease = a_running_lease()
    other = a_running_lease()
    foreign = make_document(lease=other, title="Someone else's receipt")
    shared = make_document(lease=lease, title="Deposit receipt", tenant_visible=True)

    with pytest.raises(ValidationError, match="staff-only document filed against this tenancy"):
        receive(lease, "1000.00", evidence=foreign)
    with pytest.raises(ValidationError, match="staff-only document filed against this tenancy"):
        receive(lease, "1000.00", evidence=shared)

    staff = make_document(lease=lease, title="Deposit receipt")
    receive(lease, "1000.00", evidence=staff)
    assert deposits.held(lease) == Decimal("1000.00")


def test_no_deposit_entry_is_inferred_from_the_lease_term():
    lease = a_running_lease(deposit=Decimal("2500.00"))

    assert not DepositEntry.objects.filter(lease=lease).exists()
    assert deposits.held(lease) == ZERO
    assert deposits.addressed(lease) is False
