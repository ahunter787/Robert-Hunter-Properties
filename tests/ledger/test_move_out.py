"""The move-out statement and how a retained deposit reaches the charges (E5, ADR-031).

The case: a tenancy ends owing $300, and the $500 deposit was retained. Industry practice
is to apply the permitted deposit against the final charges, refund the rest, and send one
itemised accounting. The deposit is not new cash and not rent: applying it moves held
tenant money against a bill, and the statement explains the result.
"""

import datetime as dt
import itertools
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.ledger import deposits, finance_reviews, services, statements
from apps.ledger.models import FundsApplication
from tests.factories import (
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_tenant,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")
_MANAGERS = itertools.count(1)


def new_manager():
    return make_manager(username=f"move-out-manager-{next(_MANAGERS)}")


def ended_lease(*, balance="300.00", deposit="500.00", tenants=()):
    """An ended tenancy with one arrears charge and money on the deposit register."""
    lease = make_lease(
        tenants=list(tenants),
        start_date=TODAY - dt.timedelta(days=200),
        end_date=TODAY - dt.timedelta(days=20),
        deposit=Decimal(deposit),
    )
    if Decimal(balance) > 0:
        make_charge(lease, amount=Decimal(balance), due_date=TODAY - dt.timedelta(days=30))
    if Decimal(deposit) > 0:
        deposits.record(
            lease,
            kind="RECEIVED",
            amount=Decimal(deposit),
            date=TODAY - dt.timedelta(days=200),
        )
    lease_services.end_lease(
        lease,
        ended_on=TODAY - dt.timedelta(days=10),
        reason="END_OF_TERM",
        note="Term ran out",
        keep=[charge.pk for charge in lease.charges.all()],
        forwarding_address="1 New Address, Portland, OR 97201",
        actor=new_manager(),
    )
    lease.refresh_from_db()
    return lease


def target_key(lease):
    return next(iter(finance_reviews.targets(services.build_ledger(lease))))


def withhold(lease, amount="500.00", reason="Unpaid rent and cleaning"):
    return deposits.record(
        lease,
        kind="WITHHELD",
        amount=Decimal(amount),
        date=TODAY,
        reason=reason,
        actor=new_manager(),
    )


def apply_deposit(lease, entry, amount, target_key, *, actor=None):
    """Run the reviewed credit action with the retained deposit as its source."""
    actor = actor or new_manager()
    prepared = finance_reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"deposit:{entry.pk}",
            "target": target_key,
            "amount": str(amount),
            "reason": "Deposit retained applied to the final balance",
        },
    )
    finance_reviews.confirm(lease.pk, token=prepared["token"], actor=actor)
    return prepared


# --- the statement --------------------------------------------------------


def test_the_move_out_statement_totals_charges_payments_and_the_deposit():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    apply_deposit(lease, entry, "300.00", target_key(lease))

    statement = statements.build(lease)

    assert statement.charged == Decimal("300.00")
    assert statement.paid == ZERO
    assert statement.deposit_received == Decimal("500.00")
    assert statement.deposit_withheld == Decimal("500.00")
    assert statement.deposit_applied == Decimal("300.00")
    assert statement.deposit_held == ZERO
    assert statement.balance_due == ZERO
    assert statement.outcome == statements.OUTCOME_ZERO
    assert statement.forwarding_address.startswith("1 New Address")


def test_the_statement_says_who_owes_whom():
    tenant_owes = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(tenant_owes)
    apply_deposit(tenant_owes, entry, "200.00", target_key(tenant_owes))
    statement = statements.build(tenant_owes)
    assert statement.tenant_owes == Decimal("100.00")
    assert statement.outcome == statements.OUTCOME_TENANT_OWES

    property_owes = make_lease(
        start_date=TODAY - dt.timedelta(days=200),
        end_date=TODAY - dt.timedelta(days=20),
        deposit=Decimal("300.00"),
    )
    deposits.record(
        property_owes,
        kind="RECEIVED",
        amount=Decimal("300.00"),
        date=TODAY - dt.timedelta(days=100),
    )
    lease_services.end_lease(
        property_owes,
        ended_on=TODAY,
        reason="END_OF_TERM",
        note="Term ran out",
        actor=new_manager(),
    )
    property_owes.refresh_from_db()
    statement = statements.build(property_owes)
    assert statement.deposit_held == Decimal("300.00")
    assert statement.outcome == statements.OUTCOME_PROPERTY_OWES
    assert statement.property_owes == Decimal("300.00")


def test_a_withheld_deposit_is_a_credit_source_but_not_tenant_spendable_credit():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    ledger = services.build_ledger(lease)

    source = next(row for row in ledger.credit_sources if row["value"] == f"deposit:{entry.pk}")
    assert source["available"] == Decimal("500.00")
    assert source["is_deposit"] is True
    assert ledger.credit == ZERO, "retained deposit is not the tenant's spendable credit"


def test_applying_the_retained_deposit_settles_the_charge_and_is_audited():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    target = target_key(lease)
    apply_deposit(lease, entry, "300.00", target)

    assert services.build_ledger(lease).balance_due == ZERO
    applications = FundsApplication.objects.filter(lease=lease, source_deposit=entry)
    assert applications.count() == 1
    assert applications.get().amount == Decimal("300.00")
    assert AuditEvent.objects.filter(lease=lease, action=AuditAction.CHARGE_ADJUSTED).exists()


def test_a_retained_deposit_cannot_be_applied_beyond_what_is_owed():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    target = target_key(lease)

    with pytest.raises(ValidationError, match="available credit"):
        finance_reviews.prepare(
            lease,
            actor=new_manager(),
            action="apply",
            data={
                "source": f"deposit:{entry.pk}",
                "target": target,
                "amount": "400.00",
                "reason": "Too much",
            },
        )


def test_undoing_the_application_reopens_the_balance_and_the_deposit():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    target = target_key(lease)
    apply_deposit(lease, entry, "300.00", target)
    application = FundsApplication.objects.get(source_deposit=entry)
    manager = new_manager()

    prepared = finance_reviews.prepare(
        lease,
        actor=manager,
        action="undo",
        application=application.pk,
        data={"reason": "Applied to the wrong tenancy"},
    )
    finance_reviews.confirm(lease.pk, token=prepared["token"], actor=manager)

    assert services.build_ledger(lease).balance_due == Decimal("300.00")
    assert FundsApplication.objects.filter(reverses=application).exists()


# --- forwarding, issuance, screens ----------------------------------------


def test_the_end_form_captures_the_forwarding_address():
    lease = make_lease(end_date=TODAY + dt.timedelta(days=30))
    lease_services.end_lease(
        lease,
        ended_on=TODAY,
        reason="END_OF_TERM",
        note="Term ended early by agreement",
        forwarding_address="9 Forward Way, Salem, OR 97301",
        actor=new_manager(),
    )
    lease.refresh_from_db()
    assert lease.forwarding_address == "9 Forward Way, Salem, OR 97301"
    event = AuditEvent.objects.get(lease=lease, action=AuditAction.LEASE_ENDED)
    assert event.metadata["forwarding_address"].startswith("9 Forward")


def test_a_manager_can_record_and_change_the_forwarding_address(client):
    lease = ended_lease(balance="0", deposit="0")
    client.force_login(make_manager())

    response = client.post(
        reverse("ledger:move-out", args=[lease.pk]),
        {"action": "address", "forwarding_address": "2 Later Street, Bend, OR 97701"},
    )

    assert response.status_code == 302
    lease.refresh_from_db()
    assert lease.forwarding_address == "2 Later Street, Bend, OR 97701"
    assert AuditEvent.objects.filter(
        lease=lease, action=AuditAction.MOVE_OUT_DETAILS_UPDATED
    ).exists()


def test_issuing_the_statement_records_an_immutable_snapshot():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    apply_deposit(lease, entry, "300.00", target_key(lease))
    manager = new_manager()

    event = statements.issue(lease, actor=manager, note="Emailed and posted to the portal")
    again = statements.issue(lease, actor=manager, note="Corrected copy")

    assert event.pk != again.pk
    assert statements.latest(lease).pk == again.pk
    assert (
        AuditEvent.objects.filter(lease=lease, action=AuditAction.MOVE_OUT_STATEMENT_ISSUED).count()
        == 2
    )
    assert "statement" in statements.latest(lease).metadata
    assert "Emailed" in event.metadata["note"]
    assert "Corrected" in again.metadata["note"]


def test_the_statement_is_only_issued_after_the_tenancy_ends():
    lease = make_lease()

    with pytest.raises(ValidationError, match="after the tenancy ends"):
        statements.issue(lease, actor=new_manager())


def test_manager_statement_page_shows_the_deposit_and_outcome(client):
    lease = ended_lease(balance="300.00", deposit="500.00")
    withhold(lease)
    client.force_login(make_manager())

    body = strip_tags(client.get(reverse("ledger:move-out", args=[lease.pk])).content.decode())

    assert "Move-out statement" in body
    assert "Deposit withheld" in body
    assert "Unpaid rent and cleaning" in body
    assert "Tenant owes" in body


def test_the_credit_screen_offers_the_retained_deposit(client):
    lease = ended_lease(balance="300.00", deposit="500.00")
    withhold(lease)
    client.force_login(new_manager())

    body = strip_tags(client.get(reverse("ledger:credit-apply", args=[lease.pk])).content.decode())

    assert "Deposit retained" in body
    assert "Apply available credit" in body or "Apply credit" in body


def test_the_tenant_sees_their_own_final_statement_only(client):
    tenant = make_tenant(username="final-tenant")
    lease = ended_lease(balance="300.00", deposit="500.00", tenants=[tenant])
    withhold(lease)
    client.force_login(tenant)

    response = client.get(reverse("payments:final-statement"))
    body = strip_tags(response.content.decode())

    assert response.status_code == 200
    assert "Final statement" in body
    assert "Unpaid rent and cleaning" in body
    assert "Deposit withheld" in body
    payments = strip_tags(client.get(reverse("payments:home")).content.decode())
    assert "Read your final statement" in payments


def test_a_tenant_without_an_ended_tenancy_gets_no_statement(client):
    client.force_login(make_tenant(username="no-final"))

    body = client.get(reverse("payments:final-statement")).content.decode()

    assert "available after the tenancy ends" in body


def test_a_tenant_cannot_reach_the_manager_statement_screen(client):
    lease = ended_lease(balance="0", deposit="0")
    client.force_login(make_tenant(username="outsider"))

    assert client.get(reverse("ledger:move-out", args=[lease.pk])).status_code == 403


# --- settlement and invariants --------------------------------------------


def test_settling_after_the_deposit_is_applied_and_returned():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease, "300.00")
    apply_deposit(lease, entry, "300.00", target_key(lease))
    deposits.record(lease, kind="RETURNED", amount=Decimal("200.00"), date=TODAY)

    lease_services.settle_account(lease)
    lease.refresh_from_db()
    assert lease.account_status == "SETTLED"
    assert statements.build(lease).outcome == statements.OUTCOME_ZERO


def test_an_application_has_exactly_one_source():
    lease = ended_lease(balance="300.00", deposit="500.00")
    entry = withhold(lease)
    charge = lease.charges.filter(kind="MANUAL").first() or lease.charges.first()
    payment = make_payment(lease, amount=Decimal("10.00"))

    with pytest.raises(IntegrityError), transaction.atomic():
        FundsApplication.objects.create(
            lease=lease,
            source_deposit=entry,
            source_payment=payment,
            target=charge,
            amount=Decimal("1.00"),
        )
