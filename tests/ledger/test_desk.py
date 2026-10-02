"""The ledger desk: generating rent, charging, paying, reversing, adjusting."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ledger import services
from apps.ledger.models import Charge, ChargeKind, Direction, Payment, PaymentStatus
from tests.factories import (
    make_admin,
    make_charge,
    make_lease,
    make_manager,
    make_payment,
    make_tenant,
    make_unit,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def signed_in(client):
    client.force_login(make_manager(username="ledger-manager"))
    return client


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="ledger-admin"))
    return client


# --- generating rent -----------------------------------------------------


def test_a_manager_creates_the_missing_rent_charges(signed_in):
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 12, 31), rent_due_day=1
    )

    response = signed_in.post(reverse("ledger:rent-charges", args=[lease.pk]))

    assert response.status_code == 302
    assert Charge.objects.filter(lease=lease, kind=ChargeKind.RENT).exists()


def test_creating_rent_charges_twice_is_reported_as_nothing_to_do(signed_in):
    lease = make_lease(
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 12, 31), rent_due_day=1
    )
    signed_in.post(reverse("ledger:rent-charges", args=[lease.pk]))
    before = Charge.objects.count()

    response = signed_in.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    assert Charge.objects.count() == before
    assert b"already charged" in response.content


def test_rent_charges_cannot_be_created_for_a_draft(signed_in):
    from apps.leases.models import LeaseStatus

    lease = make_lease(status=LeaseStatus.DRAFT)

    response = signed_in.post(reverse("ledger:rent-charges", args=[lease.pk]), follow=True)

    assert not Charge.objects.exists()
    assert b"draft lease" in response.content.lower() or b"Activate the lease" in response.content


# --- charging ------------------------------------------------------------


def test_a_manager_adds_a_manual_charge(signed_in):
    lease = make_lease()

    response = signed_in.post(
        reverse("ledger:charge-create", args=[lease.pk]),
        {"description": "Replacement keys", "amount": "45.00", "due_date": TODAY.isoformat()},
    )

    assert response.status_code == 302
    charge = Charge.objects.get()
    assert charge.kind == ChargeKind.MANUAL
    assert charge.amount == Decimal("45.00")
    assert charge.created_by is not None
    assert services.build_ledger(lease).balance_due == Decimal("45.00")


def test_a_charge_of_zero_is_refused(signed_in):
    lease = make_lease()

    response = signed_in.post(
        reverse("ledger:charge-create", args=[lease.pk]),
        {"description": "Nothing", "amount": "0.00", "due_date": TODAY.isoformat()},
    )

    assert response.status_code == 200
    assert not Charge.objects.exists()


def test_a_charge_cannot_carry_more_than_two_decimals(signed_in):
    lease = make_lease()

    response = signed_in.post(
        reverse("ledger:charge-create", args=[lease.pk]),
        {"description": "Odd", "amount": "10.005", "due_date": TODAY.isoformat()},
    )

    assert response.status_code == 200
    assert not Charge.objects.exists()


# --- payments ------------------------------------------------------------


def test_a_manager_records_a_cleared_payment(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY)

    response = signed_in.post(
        reverse("ledger:payment-create", args=[lease.pk]),
        {
            "amount": "1850.00",
            "payment_date": TODAY.isoformat(),
            "method": "ACH",
            "status": PaymentStatus.CLEARED,
            "external_reference": "ACH-123",
            "notes": "",
        },
    )

    assert response.status_code == 302
    assert services.build_ledger(lease).balance_due == Decimal("0.00")


def test_a_manager_records_a_pending_payment_which_does_not_settle_anything(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY)

    signed_in.post(
        reverse("ledger:payment-create", args=[lease.pk]),
        {
            "amount": "1850.00",
            "payment_date": TODAY.isoformat(),
            "method": "ACH",
            "status": PaymentStatus.PENDING,
            "external_reference": "",
            "notes": "",
        },
    )

    ledger = services.build_ledger(lease)
    assert ledger.balance_due == Decimal("1850.00")
    assert ledger.charges[0].state == "PENDING"


def test_a_manager_clears_a_pending_payment(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY)
    payment = make_payment(
        lease, amount=Decimal("1850.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )

    response = signed_in.post(reverse("ledger:payment-clear", args=[payment.pk]))

    payment.refresh_from_db()
    assert response.status_code == 302
    assert payment.status == PaymentStatus.CLEARED
    assert services.build_ledger(lease).balance_due == Decimal("0.00")


def test_a_manager_voids_a_pending_payment(signed_in):
    lease = make_lease()
    payment = make_payment(
        lease, amount=Decimal("1850.00"), payment_date=TODAY, status=PaymentStatus.PENDING
    )

    response = signed_in.post(
        reverse("ledger:payment-void", args=[payment.pk]), {"reason": "never arrived"}
    )

    payment.refresh_from_db()
    assert response.status_code == 302
    assert payment.status == PaymentStatus.VOID


def test_a_cleared_payment_cannot_be_cleared_again(signed_in):
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("10.00"), payment_date=TODAY)

    response = signed_in.post(reverse("ledger:payment-clear", args=[payment.pk]), follow=True)

    assert b"Only a pending payment" in response.content


# --- reversals (admin only) ----------------------------------------------


def test_an_admin_reverses_a_payment(as_admin):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    confirm = as_admin.get(reverse("ledger:payment-reverse", args=[payment.pk]))
    assert confirm.status_code == 200
    assert b"1000.00" in confirm.content or b"1,000.00" in confirm.content

    response = as_admin.post(
        reverse("ledger:payment-reverse", args=[payment.pk]), {"reason": "check bounced"}
    )

    assert response.status_code == 302
    assert Payment.objects.count() == 2
    assert services.build_ledger(lease).balance_due == Decimal("1000.00")


def test_a_reversal_needs_a_reason(as_admin):
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    response = as_admin.post(reverse("ledger:payment-reverse", args=[payment.pk]), {"reason": ""})

    assert response.status_code == 200
    assert Payment.objects.count() == 1


def test_a_payment_cannot_be_reversed_twice_through_the_screen(as_admin):
    lease = make_lease()
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)
    services.reverse_payment(payment, reason="first")

    response = as_admin.post(
        reverse("ledger:payment-reverse", args=[payment.pk]), {"reason": "second"}, follow=True
    )

    assert b"already been reversed" in response.content
    assert Payment.objects.filter(kind="REVERSAL").count() == 1


# --- adjustments (admin only) --------------------------------------------


def test_an_admin_reduces_a_charge_with_an_adjustment(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    confirm = as_admin.get(reverse("ledger:charge-adjust", args=[charge.pk]))
    assert confirm.status_code == 200

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {"direction": Direction.DECREASE, "amount": "250.00", "reason": "overcharged"},
    )

    charge.refresh_from_db()
    assert response.status_code == 302
    assert charge.amount == Decimal("1000.00")
    assert services.build_ledger(lease).balance_due == Decimal("750.00")


def test_an_adjustment_needs_a_reason_through_the_screen(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {"direction": Direction.DECREASE, "amount": "250.00", "reason": ""},
    )

    assert response.status_code == 200
    assert Charge.objects.count() == 1


def test_a_manager_cannot_reverse_or_adjust(signed_in):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    payment = make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    assert signed_in.get(reverse("ledger:payment-reverse", args=[payment.pk])).status_code == 403
    assert (
        signed_in.post(
            reverse("ledger:payment-reverse", args=[payment.pk]), {"reason": "no"}
        ).status_code
        == 403
    )
    assert signed_in.get(reverse("ledger:charge-adjust", args=[charge.pk])).status_code == 403


# --- the screens ---------------------------------------------------------


def test_the_ledger_shows_the_balance_and_every_entry(signed_in):
    lease = make_lease(monthly_rent=Decimal("1850.00"))
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY, description="Rent for this month")
    make_payment(lease, amount=Decimal("500.00"), payment_date=TODAY)

    body = signed_in.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()

    assert "1,350.00" in body, "the balance is derived, not stored"
    assert "Rent for this month" in body
    assert "Partly paid" in body


def test_the_ledger_of_a_draft_says_there_is_no_ledger_yet(signed_in):
    from apps.leases.models import LeaseStatus

    lease = make_lease(status=LeaseStatus.DRAFT)

    body = signed_in.get(reverse("ledger:lease-ledger", args=[lease.pk])).content.decode()

    assert "No ledger yet" in body
    assert "Create rent charges" not in body


def test_the_overview_lists_balances_and_totals(signed_in):
    lease = make_lease()
    make_charge(lease, amount=Decimal("1850.00"), due_date=TODAY)

    body = signed_in.get(reverse("ledger:overview")).content.decode()

    assert "Outstanding" in body
    assert "1,850.00" in body
    assert lease.unit.identifier in body


def test_the_overview_can_filter_to_overdue_leases(signed_in):
    overdue_lease = make_lease()
    make_charge(overdue_lease, amount=Decimal("100.00"), due_date=TODAY - dt.timedelta(days=10))
    settled_lease = make_lease()
    make_charge(settled_lease, amount=Decimal("100.00"), due_date=TODAY)

    response = signed_in.get(reverse("ledger:overview"), {"overdue": "1"})
    rows = response.context["rows"]

    assert [row.lease.pk for row in rows] == [overdue_lease.pk]


def test_the_overview_searches_by_tenant_or_unit(signed_in):
    wanted = make_lease(
        make_unit(identifier="Storefront"),
        tenants=[make_tenant(username="ada", first_name="Ada", last_name="Lovelace")],
    )
    make_lease(make_unit(identifier="Backflat"))
    make_charge(wanted, amount=Decimal("10.00"), due_date=TODAY)

    response = signed_in.get(reverse("ledger:overview"), {"q": "Lovelace"})

    assert [row.lease.pk for row in response.context["rows"]] == [wanted.pk]


# --- zeroing a charge from the adjust screen ------------------------------


def test_the_adjustment_amount_starts_at_what_is_still_owed(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("400.00"), payment_date=TODAY)

    response = as_admin.get(reverse("ledger:charge-adjust", args=[charge.pk]))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["form"]["amount"].value() == Decimal("600.00")
    assert "Still owed" in body
    assert "600.00" in body


def test_submitting_the_prefilled_amount_zeroes_the_charge(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {"direction": Direction.DECREASE, "amount": "1000.00", "reason": "raised in error"},
    )

    assert response.status_code == 302
    assert services.build_ledger(lease).balance_due == Decimal("0.00")


def test_the_quick_button_credits_the_full_charge(as_admin):
    """The part-paid case: the whole charge should go, not just the remainder."""
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("400.00"), payment_date=TODAY)

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {
            "direction": Direction.DECREASE,
            "amount": "600.00",  # what the page prefilled
            "reason": "raised in error",
            "use_full_amount": "1",
        },
    )

    assert response.status_code == 302
    adjustment = Charge.objects.get(kind=ChargeKind.ADJUSTMENT)
    assert adjustment.amount == Decimal("1000.00"), "the full amount, not the remainder"
    assert services.build_ledger(lease).balance_due == Decimal("-400.00"), "in credit"


def test_the_quick_button_does_not_inflate_an_increase(as_admin):
    """On a debit adjustment the submitted amount stands; nothing is auto-filled."""
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {
            "direction": Direction.INCREASE,
            "amount": "25.00",
            "reason": "extra works",
            "use_full_amount": "1",
        },
    )

    assert response.status_code == 302
    assert Charge.objects.get(kind=ChargeKind.ADJUSTMENT).amount == Decimal("25.00")


def test_a_settled_charge_is_not_prefilled(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000.00"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1000.00"), payment_date=TODAY)

    response = as_admin.get(reverse("ledger:charge-adjust", args=[charge.pk]))
    body = response.content.decode()

    assert response.context["form"]["amount"].value() in (None, "")
    assert "already settled" in body
    assert "use_full_amount" not in body


def test_the_adjust_page_still_needs_a_reason(as_admin):
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("100.00"), due_date=TODAY)

    response = as_admin.post(
        reverse("ledger:charge-adjust", args=[charge.pk]),
        {"direction": Direction.DECREASE, "amount": "100.00", "reason": ""},
    )

    assert response.status_code == 200
    assert not Charge.objects.filter(kind=ChargeKind.ADJUSTMENT).exists()
