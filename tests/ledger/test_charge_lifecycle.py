"""P4: what a tenancy's money may do — while it runs, after it ends, once it is settled.

The rule the owner set (P4-Q1, P4-Q3): recurring charges stop when a tenancy ends, the money
already charged stays correctable, and a settled tenancy is closed for good. Post-tenancy
charges — a damage recharge carrying its reason code, its lease clause and its evidence — are
deliberately **not** here: they wait for Phase 6 so a charge always has its evidence (P4-E6),
and the seam they will use is marked in `refuse_if_not_chargeable`.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.leases import services as lease_services
from apps.leases.models import EndReason, LeaseAccountStatus, LeaseStatus
from apps.ledger import services as ledger_services
from apps.ledger.models import Charge, ChargeKind, Direction, PaymentStatus
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_superadmin,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def a_running_tenancy(**fields):
    """A tenancy running from the start of this month, falling due on the 1st."""
    fields.setdefault("start_date", TODAY.replace(day=1) - dt.timedelta(days=60))
    fields.setdefault("end_date", TODAY + dt.timedelta(days=300))
    fields.setdefault("rent_due_day", 1)
    fields.setdefault("deposit", Decimal("0.00"))
    if "tenants" not in fields:
        # Built lazily: setdefault would create the default tenant even when the caller
        # passes their own, and the second "ada" collides with the first.
        fields["tenants"] = [make_tenant(username="ada")]
    return make_lease(**fields)


def end_it(lease, *, ended_on=None, keep=(), reason=EndReason.END_OF_TERM, note="Term ran out."):
    return lease_services.end_lease(
        lease,
        ended_on=ended_on or TODAY,
        reason=reason,
        note=note,
        keep=keep,
    )


# --- the guard (P4-Q3, P4-Q4) ----------------------------------------------


def test_a_running_tenancy_takes_charges():
    lease = a_running_tenancy()

    created = ledger_services.generate_charges(lease, through=TODAY)

    assert created, "the month's rent has fallen due"
    assert lease.can_be_charged is True


def test_an_ended_tenancy_refuses_generated_charges():
    lease = a_running_tenancy()
    end_it(lease)

    with pytest.raises(ValidationError, match="has ended"):
        ledger_services.generate_charges(lease, through=TODAY)

    assert lease.charges.count() == 0


def test_an_ended_tenancy_refuses_a_one_off_charge():
    lease = a_running_tenancy()
    end_it(lease)

    with pytest.raises(ValidationError, match="has ended"):
        ledger_services.create_charge(
            lease, description="Damage", amount=Decimal("100.00"), due_date=TODAY
        )


def test_a_settled_tenancy_refuses_everything():
    lease = a_running_tenancy()
    end_it(lease)
    lease_services.settle_account(lease)

    for call in (
        lambda: ledger_services.generate_charges(lease, through=TODAY),
        lambda: ledger_services.create_charge(
            lease, description="Damage", amount=Decimal("100.00"), due_date=TODAY
        ),
    ):
        with pytest.raises(ValidationError, match="settled"):
            call()


def test_reopening_an_account_never_reopens_occupancy_or_allows_new_charges():
    """A charge for damage after a tenancy ends is refused *for now*, and here is why.

    P4-E6 adds a charge kind carrying a reason code, the lease clause it rests on and its
    evidence, and it will relax exactly one line: the refusal in `refuse_if_not_chargeable`.
    Reopening the financial account permits corrections, but never restores occupancy.
    """
    lease = a_running_tenancy()
    end_it(lease)

    with pytest.raises(ValidationError):
        ledger_services.create_charge(
            lease, description="Cleaning", amount=Decimal("250.00"), due_date=TODAY
        )

    lease_services.settle_account(lease)
    lease_services.reopen_account(lease, reason="Cleaning invoice arrived after move-out.")
    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ENDED
    assert lease.account_status == LeaseAccountStatus.OPEN
    with pytest.raises(ValidationError, match="has ended"):
        ledger_services.create_charge(
            lease, description="Cleaning", amount=Decimal("250.00"), due_date=TODAY
        )


def test_money_in_and_corrections_still_work_on_an_ended_tenancy():
    lease = a_running_tenancy()
    ledger_services.generate_charges(lease, through=TODAY)
    charge = lease.charges.filter(kind=ChargeKind.RENT).order_by("due_date").first()
    end_it(lease)

    ledger_services.record_payment(
        lease, amount=Decimal("100.00"), payment_date=TODAY, method="CHECK"
    )
    adjustment = ledger_services.create_adjustment(
        charge, direction=Direction.DECREASE, amount=Decimal("50.00"), reason="Agreed"
    )

    assert lease.payments.count() == 1
    assert adjustment.adjusts == charge
    ledger = ledger_services.build_ledger(lease)
    charged = sum((row.amount for row in lease.charges.filter(kind=ChargeKind.RENT)), Decimal("0"))
    assert ledger.balance_due == charged - Decimal("150.00")


# --- the close-out (P4-Q2) --------------------------------------------------


def test_a_future_month_is_cancelled_by_an_adjustment_never_deleted():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=200))
    future = make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY + dt.timedelta(days=30))

    adjustments = end_it(lease)

    future.refresh_from_db()
    assert Charge.objects.filter(pk=future.pk).exists(), "the charge is not deleted"
    assert len(adjustments) == 1
    assert adjustments[0].adjusts == future
    assert adjustments[0].direction == Direction.DECREASE
    assert "Tenancy ended" in adjustments[0].reason
    assert ledger_services.build_ledger(lease).balance_due == Decimal("0.00")


def test_a_kept_month_stays_exactly_as_it_was():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=200))
    keep_this = make_charge(
        lease, amount=Decimal("1850.00"), due_date=TODAY + dt.timedelta(days=30)
    )
    cancel_this = make_charge(
        lease, amount=Decimal("120.00"), due_date=TODAY + dt.timedelta(days=40)
    )

    adjustments = end_it(lease, keep=[keep_this.pk])

    assert [adjustment.adjusts for adjustment in adjustments] == [cancel_this]
    assert ledger_services.build_ledger(lease).balance_due == keep_this.amount


def test_only_the_months_the_schedule_raised_are_closed_out():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=200))
    manual = make_charge(
        lease,
        kind=ChargeKind.MANUAL,
        amount=Decimal("75.00"),
        due_date=TODAY + dt.timedelta(days=10),
    )
    opening = make_charge(
        lease,
        kind=ChargeKind.OPENING,
        amount=Decimal("500.00"),
        due_date=TODAY + dt.timedelta(days=20),
    )

    adjustments = end_it(lease)

    assert adjustments == [], "a one-off charge and a brought-forward balance are decisions"
    assert Charge.objects.filter(pk__in=[manual.pk, opening.pk]).count() == 2


def test_a_month_already_charged_for_the_month_it_ends_in_is_left_alone():
    lease = a_running_tenancy()
    rent = make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY.replace(day=1))

    adjustments = end_it(lease, ended_on=TODAY)

    assert adjustments == [], "the charge falls before the end date"
    assert ledger_services.build_ledger(lease).balance_due == rent.amount


def test_ending_twice_over_is_a_no_op_for_the_money():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=120))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY + dt.timedelta(days=30))
    end_it(lease)

    assert ledger_services.close_out_lease(lease, on=TODAY) == [], "already closed out"


def test_ending_refuses_a_bad_date_a_missing_reason_and_a_settled_tenancy():
    lease = a_running_tenancy()
    with pytest.raises(ValidationError, match="cannot end before it starts"):
        end_it(lease, ended_on=lease.start_date - dt.timedelta(days=1))
    with pytest.raises(ValidationError, match="why the tenancy is ending"):
        end_it(lease, reason="")
    with pytest.raises(ValidationError, match="detail behind the reason"):
        end_it(lease, note="  ")

    end_it(lease)
    with pytest.raises(ValidationError, match="Only a running tenancy|settled"):
        end_it(lease)


def test_the_end_records_who_why_and_what_it_cancelled():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=90))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY + dt.timedelta(days=30))
    admin = make_admin(username="ending-admin")

    lease_services.end_lease(
        lease,
        ended_on=TODAY,
        reason=EndReason.EVICTION,
        note="Served 1 October.",
        actor=admin,
    )

    event = AuditEvent.objects.for_lease(lease).filter(action=AuditAction.LEASE_ENDED).first()
    assert event.actor == admin
    assert event.metadata["end_reason"] == "EVICTION"
    assert event.metadata["closed_out"] == 1
    assert "eviction" in event.summary.lower()


# --- settling and reopening (P4-Q1) ----------------------------------------


def test_settling_refuses_while_anything_is_owed():
    lease = a_running_tenancy()
    ledger_services.generate_charges(lease, through=TODAY)
    end_it(lease)

    with pytest.raises(ValidationError, match="still owed"):
        lease_services.settle_account(lease)


def test_settling_refuses_while_money_is_held():
    lease = a_running_tenancy()
    make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)
    end_it(lease)

    with pytest.raises(ValidationError, match="still held"):
        lease_services.settle_account(lease)


def test_settling_refuses_a_pending_payment_and_a_recorded_deposit():
    pending_lease = a_running_tenancy()
    make_payment(
        pending_lease,
        amount=Decimal("100.00"),
        payment_date=TODAY,
        status=PaymentStatus.PENDING,
    )
    end_it(pending_lease)
    with pytest.raises(ValidationError, match="still pending"):
        lease_services.settle_account(pending_lease)

    deposit_lease = a_running_tenancy(
        deposit=Decimal("500.00"), tenants=[make_tenant(username="deposit-tenant")]
    )
    end_it(deposit_lease)
    with pytest.raises(ValidationError, match="security deposit"):
        lease_services.settle_account(deposit_lease)


def test_every_financial_mutation_requires_reopening_a_settled_account():
    lease = a_running_tenancy()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("100.00"), payment_date=TODAY)
    end_it(lease)
    lease_services.settle_account(lease)
    pending = make_payment(
        lease,
        amount=Decimal("10.00"),
        payment_date=TODAY,
        status=PaymentStatus.PENDING,
    )

    calls = (
        lambda: ledger_services.create_adjustment(
            charge,
            direction=Direction.DECREASE,
            amount=Decimal("1.00"),
            reason="Correction",
        ),
        lambda: ledger_services.record_payment(
            lease, amount=Decimal("1.00"), payment_date=TODAY, method="CHECK"
        ),
        lambda: ledger_services.reverse_payment(payment, reason="Correction"),
        lambda: ledger_services.clear_payment(pending),
        lambda: ledger_services.void_payment(pending, reason="Correction"),
    )
    for call in calls:
        with pytest.raises(ValidationError, match="financial account is settled"):
            call()


def test_a_stale_lease_object_cannot_bypass_account_settlement():
    from apps.leases.models import Lease

    lease = a_running_tenancy()
    end_it(lease)
    stale_lease = Lease.objects.get(pk=lease.pk)
    lease_services.settle_account(lease)

    with pytest.raises(ValidationError, match="financial account is settled"):
        ledger_services.record_payment(
            stale_lease, amount=Decimal("1.00"), payment_date=TODAY, method="CHECK"
        )


def test_settling_at_zero_closes_the_tenancy_for_good():
    lease = a_running_tenancy()
    end_it(lease)
    admin = make_admin(username="settling-admin")

    lease_services.settle_account(lease, note="Everything accounted for.", actor=admin)

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ENDED
    assert lease.account_status == LeaseAccountStatus.SETTLED
    assert lease.settled_at is not None
    assert lease.settled_by == admin
    assert lease.is_settled is True
    assert lease.is_editable is False
    event = AuditEvent.objects.for_lease(lease).filter(action=AuditAction.LEASE_SETTLED).first()
    assert event.actor == admin and "settled" in event.summary


def test_settling_needs_a_tenancy_that_has_ended():
    lease = a_running_tenancy()

    with pytest.raises(ValidationError, match="has ended can be settled"):
        lease_services.settle_account(lease)


def test_the_database_refuses_a_settled_active_tenancy():
    lease = a_running_tenancy()
    lease.account_status = LeaseAccountStatus.SETTLED
    lease.settled_at = timezone.now()

    with pytest.raises(IntegrityError), transaction.atomic():
        lease.save(update_fields=["account_status", "settled_at"])


def test_reopening_changes_only_the_financial_account_and_keeps_the_record():
    lease = a_running_tenancy(end_date=TODAY + dt.timedelta(days=90))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY + dt.timedelta(days=30))
    end_it(lease)
    assert lease.charges.filter(kind=ChargeKind.ADJUSTMENT).exists()
    lease_services.settle_account(lease)

    lease_services.reopen_account(lease, reason="Invoice arrived after the tenancy ended.")

    lease.refresh_from_db()
    assert lease.status == LeaseStatus.ENDED
    assert lease.account_status == LeaseAccountStatus.OPEN
    assert lease.ended_on == TODAY
    assert lease.end_reason == EndReason.END_OF_TERM, "why it ended once is still on the record"
    assert lease.can_be_charged is False
    assert lease.charges.filter(kind=ChargeKind.ADJUSTMENT).exists(), "the close-out stands"
    assert AuditEvent.objects.for_lease(lease).filter(action=AuditAction.LEASE_REOPENED).exists()
    with pytest.raises(ValidationError, match="has ended"):
        ledger_services.generate_charges(lease, through=TODAY)


def test_reopening_an_open_account_is_refused():
    lease = a_running_tenancy()
    end_it(lease)
    with pytest.raises(ValidationError, match="Only a settled financial account"):
        lease_services.reopen_account(lease, reason="Too late.")


def test_reopening_needs_a_reason():
    lease = a_running_tenancy()
    end_it(lease)
    lease_services.settle_account(lease)

    with pytest.raises(ValidationError, match="why the tenancy is being reopened"):
        lease_services.reopen_account(lease, reason="   ")


# --- what the screens do (P4-Q4, P4-Q5) ------------------------------------


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="charge-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="charge-manager"))
    return client


@pytest.fixture
def as_superadmin(client):
    client.force_login(make_superadmin(username="charge-root"))
    return client


def test_the_ledger_stops_offering_to_charge_an_ended_tenancy(as_admin):
    lease = a_running_tenancy()
    end_it(lease)

    body = as_admin.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()

    assert "Post due rent charges" not in body
    assert "Add one-time charge" not in body
    assert "Record payment" in body, "arrears still get paid"
    assert "Occupancy: Ended" in body and "Account status" in body


def test_posting_the_charge_urls_on_an_ended_tenancy_is_refused(as_admin):
    lease = a_running_tenancy()
    end_it(lease)

    generated = as_admin.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)
    manual = as_admin.post(
        reverse("ledger:charge-create", args=[lease.pk]),
        {"description": "Damage", "amount": "100.00", "due_date": TODAY.isoformat()},
    )

    assert b"has ended" in generated.content
    assert manual.status_code == 200 and b"has ended" in manual.content
    assert not lease.charges.exclude(kind=ChargeKind.ADJUSTMENT).exists()


def test_managers_can_settle_and_reopen_financial_accounts():
    from django.test import Client

    lease = a_running_tenancy()
    end_it(lease)

    def as_role(user):
        client = Client()
        client.force_login(user)
        return client

    settle = reverse("leases:lease-settle", args=[lease.pk])
    reopen = reverse("leases:lease-reopen", args=[lease.pk])

    assert as_role(make_manager(username="m")).get(settle).status_code == 200
    assert as_role(make_admin(username="a")).get(settle).status_code == 200
    lease_services.settle_account(lease)
    assert as_role(make_manager(username="m2")).get(reopen).status_code == 200
    assert as_role(make_admin(username="a2")).get(reopen).status_code == 200
    assert as_role(make_superadmin(username="s")).get(reopen).status_code == 200


def test_a_settled_tenancy_reads_as_closed(as_admin):
    lease = a_running_tenancy()
    end_it(lease)
    lease_services.settle_account(lease)

    lease_body = as_admin.get(reverse("leases:lease-detail", args=[lease.pk])).content.decode()
    ledger_body = as_admin.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()
    overview = as_admin.get(reverse("ledger:overview")).content.decode()

    assert "financial account is settled" in lease_body
    assert "Financial account: Settled" in ledger_body
    assert "Settled" in overview, "the row is marked rather than looking live"


def test_an_ended_tenancy_has_nothing_coming_due():
    lease = a_running_tenancy()
    ledger_services.generate_charges(lease, through=TODAY)
    assert ledger_services.build_ledger(lease).next_due_date is not None

    end_it(lease)

    ledger = ledger_services.build_ledger(lease)
    assert ledger.next_due_date is None, "nothing is coming: the tenancy has ended"
    assert ledger.next_rent_date is None


def test_a_new_tenant_on_the_same_unit_never_sees_the_old_tenancy():
    """P4-Q5: the previous tenant's ledger is the office's business, not theirs."""
    unit = make_unit()
    first = make_tenant(username="first-tenant")
    second = make_tenant(username="second-tenant")
    old = a_running_tenancy(unit=unit, tenants=[first])
    old_charge = make_charge(
        old,
        amount=Decimal("1234.56"),
        description="Rent for the old tenancy",
        due_date=TODAY - dt.timedelta(days=30),
    )
    end_it(old)
    new = make_lease(
        unit,
        tenants=[second],
        start_date=TODAY,
        end_date=TODAY + dt.timedelta(days=365),
        monthly_rent=Decimal("1900.00"),
        rent_due_day=1,
    )
    make_charge(new, amount=Decimal("1900.00"), due_date=TODAY)

    from django.test import Client

    client = Client()
    client.force_login(second)
    body = " ".join(
        client.get(reverse("payments:home")).content.decode().split()
        + client.get(reverse("tenancy:lease")).content.decode().split()
    )

    assert old_charge.description not in body
    assert "1,234.56" not in body, "the old tenancy's money is not on the new tenant's pages"
    assert "1,900.00" in body, "their own charge is"


def test_a_settled_tenancy_reads_as_settled_in_the_lease_list(as_admin):
    """Found by walking the screens after the lifecycle landed: the list said "Ended"."""
    lease = a_running_tenancy()
    end_it(lease)
    lease_services.settle_account(lease)

    body = as_admin.get(reverse("leases:lease-list")).content.decode()

    rows = body.split("<tbody")[1], "the table of leases"
    assert "settled account" in rows[0]
    assert "Ended" in rows[0], "occupancy remains ended after financial settlement"


def test_the_tenant_is_told_when_their_tenancy_ends():
    """The tenant's own page used the signed term and stayed silent on an early ending."""
    tenant = make_tenant(username="ada")
    lease = a_running_tenancy(tenants=[tenant])
    ended_on = TODAY - dt.timedelta(days=3)
    end_it(lease, ended_on=ended_on)

    from django.test import Client

    client = Client()
    client.force_login(tenant)
    body = " ".join(client.get(reverse("tenancy:lease")).content.decode().split())

    assert "This tenancy ended on" in body
    assert f"{ended_on:%b} {ended_on.day}, {ended_on.year}" in body, (
        "the day it really stopped, not the signed term"
    )
    assert "the term ran to" in body, "ended early, and it says so"


def test_a_settled_tenancy_reads_as_settled_to_its_tenant():
    tenant = make_tenant(username="ada")
    lease = a_running_tenancy(tenants=[tenant])
    end_it(lease)
    lease_services.settle_account(lease)

    from django.test import Client

    client = Client()
    client.force_login(tenant)
    lease_body = " ".join(client.get(reverse("tenancy:lease")).content.decode().split())
    dashboard = client.get(reverse("accounts:home"))
    payments = " ".join(client.get(reverse("payments:home")).content.decode().split())

    assert "the account is settled" in lease_body
    assert dashboard.status_code == 200, "a settled tenancy must not break the dashboard"
    assert "the account is settled" in payments or "Nothing" in payments or "0.00" in payments


def test_a_tenancy_ended_before_dates_were_recorded_falls_back_to_its_term():
    """The screens must never say "ended on None": the term is the honest fallback."""
    tenant = make_tenant(username="former-tenant")
    lease = make_lease(
        make_unit(),
        tenants=[tenant],
        status=LeaseStatus.ENDED,
        start_date=TODAY - dt.timedelta(days=400),
        end_date=TODAY - dt.timedelta(days=40),
    )

    assert lease.ended_on is None
    assert lease.stopped_on == lease.end_date

    from django.test import Client

    client = Client()
    client.force_login(tenant)
    body = " ".join(client.get(reverse("tenancy:lease")).content.decode().split())

    assert "This tenancy ended on" in body
    assert "None" not in body
