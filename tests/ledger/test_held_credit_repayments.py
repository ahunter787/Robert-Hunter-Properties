"""Credit is held until applied; installments never create principal."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.leases import cutover
from apps.leases.models import FinancialCutover
from apps.ledger import applications, services
from apps.ledger import finance_reviews as reviews
from apps.ledger.models import Charge, Direction, FundsApplication, RepaymentPlan
from tests.factories import make_admin, make_charge, make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def setup():
    actor = make_admin()
    date = TODAY.replace(day=1)
    cutover.confirm_date(
        actor=actor,
        token=cutover.prepare_date(actor=actor, first_native_date=date, note="Synthetic test"),
    )
    lease = make_lease(
        start_date=date - dt.timedelta(days=400),
        end_date=date + dt.timedelta(days=800),
        billing_start_date=None,
    )
    return actor, lease


def opening(setup, kind="CREDIT", amount="200"):
    actor, lease = setup
    token = cutover.prepare(
        lease,
        actor=actor,
        kind=kind,
        amount=Decimal(amount),
        note="Synthetic stated amount",
        legacy_undated=True,
    )["token"]
    entry = cutover.confirm(lease.pk, actor=actor, token=token)
    lease.refresh_from_db()
    return actor, lease, entry


def plan_data(**changes):
    return {
        "mode": "monthly",
        "first_due": TODAY,
        "monthly_amount": Decimal("500"),
        "agreed_on": TODAY,
        "agreement_source": "Synthetic phone agreement",
        "explanation": "Repay starting debt monthly alongside normal rent.",
        "reason": "Owner-authorized synthetic rehearsal",
        "correction_direction": "",
        "correction_amount": None,
        **changes,
    }


def confirm_plan(actor, lease, **changes):
    reviewed = reviews.prepare(lease, actor=actor, action="plan", data=plan_data(**changes))
    reviews.confirm(lease.pk, actor=actor, token=reviewed["token"])
    return RepaymentPlan.objects.filter(lease=lease).latest("pk")


def test_hold_apply_release_and_idempotency(setup):
    actor, lease, entry = opening(setup)
    charge = make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (1000, 200, 800)
    review = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"charge:{entry.charge_id}",
            "target": f"bill:{TODAY}",
            "amount": Decimal("200"),
            "reason": "Apply agreed credit",
        },
    )
    assert not FundsApplication.objects.exists()
    reviews.confirm(lease.pk, actor=actor, token=review["token"])
    reviews.confirm(lease.pk, actor=actor, token=review["token"])
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (800, 0, 800)
    application = FundsApplication.objects.get(target=charge)
    review = reviews.prepare(
        lease, actor=actor, action="undo", application=application.pk, data={"reason": "Undo test"}
    )
    reviews.confirm(lease.pk, actor=actor, token=review["token"])
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (1000, 200, 800)
    assert not lease.payments.exists()


def test_surplus_is_not_consumed_by_later_charge(setup):
    actor, lease, _ = opening(setup, "ZERO", "0")
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    payment = services.record_payment(
        lease, amount=Decimal("1200"), payment_date=TODAY, method="CHECK", actor=actor
    )
    make_charge(lease, amount=Decimal("400"), due_date=TODAY, kind="MANUAL")
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (400, 200, 200)
    services.reverse_payment(payment, reason="Wrong receipt", actor=actor)
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (1400, 0, 1400)


def test_11500_has_23_installments_and_no_extra_charge(setup):
    actor, lease, _ = opening(setup, "DEBT", "11500")
    plan = confirm_plan(actor, lease)
    assert plan.installments.count() == 23
    assert sum((r.amount for r in plan.installments.all()), Decimal(0)) == 11500
    ledger = services.build_ledger(lease)
    assert (ledger.balance_due, ledger.due_now, ledger.arrears, ledger.future_repayments) == (
        11500,
        500,
        0,
        11000,
    )
    assert Charge.objects.filter(lease=lease).count() == 1
    assert not lease.payments.exists()


def test_month_clamping_and_final_cents(setup):
    actor, lease, _ = opening(setup, "DEBT", "1000.01")
    first = dt.date(TODAY.year + 1, 1, 31)
    plan = confirm_plan(actor, lease, first_due=first)
    assert list(plan.installments.values_list("due_date", "amount")) == [
        (first, Decimal("500")),
        (dt.date(first.year, 2, 28), Decimal("500")),
        (dt.date(first.year, 3, 31), Decimal("0.01")),
    ]
    assert services.build_ledger(lease).due_now == 0


def test_oldest_due_payment_and_future_not_prepaid(setup):
    actor, lease, _ = opening(setup, "DEBT", "1500")
    plan = confirm_plan(actor, lease, first_due=TODAY - dt.timedelta(days=2))
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    services.record_payment(
        lease, amount=Decimal("2000"), payment_date=TODAY, method="CHECK", actor=actor
    )
    ledger = services.build_ledger(lease)
    assert ledger.due_now == 0
    assert ledger.future_repayments == 1000
    assert ledger.credit == 500
    assert (
        FundsApplication.objects.filter(
            installment_key=plan.installments.first().key, is_credit=False
        )
        .get()
        .amount
        == 500
    )


def test_pending_not_available(setup):
    actor, lease, _ = opening(setup, "ZERO", "0")
    services.record_payment(
        lease,
        amount=Decimal("500"),
        payment_date=TODAY,
        method="CHECK",
        status="PENDING",
        actor=actor,
    )
    assert services.build_ledger(lease).credit == 0
    assert not FundsApplication.objects.exists()


def test_schedule_correction_and_versions(setup):
    actor, lease, entry = opening(setup, "DEBT", "11500")
    plan = confirm_plan(actor, lease)
    with pytest.raises(ValidationError, match="together"):
        services.create_adjustment(
            entry.charge,
            direction=Direction.DECREASE,
            amount=Decimal("500"),
            reason="Must review",
            actor=actor,
        )
    new = confirm_plan(
        actor, lease, correction_direction="DECREASE", correction_amount=Decimal("500")
    )
    assert new.previous_id == plan.pk
    assert plan.installments.count() == 23
    assert new.installments.count() == 22
    assert entry.charge.amount == 11500
    assert services.build_ledger(lease).balance_due == 11000


def test_stale_wrong_actor_and_forged_targets(setup):
    actor, lease, entry = opening(setup)
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    data = {
        "source": f"charge:{entry.charge_id}",
        "target": f"bill:{TODAY}",
        "amount": Decimal("200"),
        "reason": "Test",
    }
    review = reviews.prepare(lease, actor=actor, action="apply", data=data)
    with pytest.raises(ValidationError):
        reviews.confirm(lease.pk, actor=make_manager(), token=review["token"])
    with pytest.raises(ValidationError):
        reviews.prepare(
            lease, actor=actor, action="apply", data={**data, "target": "opening:999999"}
        )
    make_charge(lease, amount=Decimal("5"), due_date=TODAY, kind="MANUAL")
    with pytest.raises(ValidationError):
        reviews.confirm(lease.pk, actor=actor, token=review["token"])
    with pytest.raises(PermissionDenied):
        reviews.prepare(lease, actor=make_tenant(), action="apply", data=data)


def test_immutable_application_and_plain_form_authorization(setup, client):
    actor, lease, _ = opening(setup)
    path = reverse("ledger:credit-apply", args=[lease.pk])
    client.force_login(make_tenant())
    assert client.get(path).status_code == 403
    client.force_login(actor)
    assert client.get(path).status_code == 200
    confirm_path = reverse("ledger:repayment-plan", args=[lease.pk])
    assert client.get(confirm_path).status_code == 200
    with pytest.raises(ValidationError):
        FinancialCutover.objects.get().delete()


def test_legacy_snapshot_preserves_coverage(setup):
    actor, _ = setup
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    from tests.factories import make_payment

    make_payment(lease, amount=Decimal("200"), payment_date=TODAY)
    before = services.build_ledger(lease)
    applications.initialize(lease)
    after = services.build_ledger(lease)
    assert before.due_now == after.due_now == 800
    assert FundsApplication.objects.get(target=charge).legacy_derived


def test_correcting_paid_charge_releases_surplus_without_receipt(setup):
    actor, lease, _ = opening(setup, "ZERO", "0")
    charge = make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    services.record_payment(
        lease, amount=Decimal("1000"), payment_date=TODAY, method="CHECK", actor=actor
    )
    services.create_adjustment(
        charge,
        direction=Direction.DECREASE,
        amount=Decimal("300"),
        reason="Overcharge",
        actor=actor,
    )
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (0, 300, -300)
    assert len(ledger.effective_payments) == 1
    assert sum((p.amount for p in ledger.effective_payments), Decimal(0)) == 1000


def test_reducing_used_credit_reopens_bill(setup):
    actor, lease, entry = opening(setup)
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    proposal = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"charge:{entry.charge_id}",
            "target": f"bill:{TODAY}",
            "amount": Decimal("200"),
            "reason": "Use credit",
        },
    )
    reviews.confirm(lease.pk, actor=actor, token=proposal["token"])
    services.create_adjustment(
        entry.charge,
        direction=Direction.INCREASE,
        amount=Decimal("50"),
        reason="Correct original credit",
        actor=actor,
    )
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (850, 0, 850)


def test_early_credit_and_partial_schedule_correction_preserve_coverage(setup):
    actor, lease, entry = opening(setup, "DEBT", "1500")
    plan = confirm_plan(actor, lease, first_due=TODAY + dt.timedelta(days=1))
    payment = services.record_payment(
        lease, amount=Decimal("400"), payment_date=TODAY, method="CHECK", actor=actor
    )
    last = plan.installments.last()
    proposal = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"payment:{payment.pk}",
            "target": f"installment:{last.key}",
            "amount": Decimal("400"),
            "reason": "Explicit early repayment",
        },
    )
    reviews.confirm(lease.pk, actor=actor, token=proposal["token"])
    replacement = confirm_plan(
        actor,
        lease,
        first_due=plan.first_due,
        correction_direction="DECREASE",
        correction_amount=Decimal("300"),
    )
    assert replacement.previous_id == plan.pk
    ledger = services.build_ledger(lease)
    assert ledger.credit == 200
    assert sum((row.paid for row in ledger.obligations), Decimal(0)) == 200
    assert ledger.unpaid_charges - ledger.credit == ledger.balance_due == 800


def test_clearing_pending_allocates_once_and_does_not_prepay(setup):
    actor, lease, _ = opening(setup, "ZERO", "0")
    make_charge(lease, amount=Decimal("200"), due_date=TODAY)
    payment = services.record_payment(
        lease,
        amount=Decimal("500"),
        payment_date=TODAY,
        method="CHECK",
        status="PENDING",
        actor=actor,
    )
    services.clear_payment(payment, actor=actor)
    with pytest.raises(ValidationError):
        services.clear_payment(payment, actor=actor)
    assert services.build_ledger(lease).credit == 300
    assert FundsApplication.objects.count() == 1


def test_undo_receipt_releases_credit_dependent_application(setup):
    actor, lease, _ = opening(setup, "ZERO", "0")
    payment = services.record_payment(
        lease, amount=Decimal("200"), payment_date=TODAY, method="CHECK", actor=actor
    )
    make_charge(lease, amount=Decimal("500"), due_date=TODAY)
    reviewed = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"payment:{payment.pk}",
            "target": f"bill:{TODAY}",
            "amount": Decimal("200"),
            "reason": "Use held receipt",
        },
    )
    reviews.confirm(lease.pk, actor=actor, token=reviewed["token"])
    services.reverse_payment(payment, reason="Receipt entered by mistake", actor=actor)
    ledger = services.build_ledger(lease)
    assert (ledger.due_now, ledger.credit, ledger.balance_due) == (500, 0, 500)


def test_signed_rollback_and_tampering(setup, monkeypatch):
    actor, lease, entry = opening(setup)
    make_charge(lease, amount=Decimal("500"), due_date=TODAY)
    reviewed = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"charge:{entry.charge_id}",
            "target": f"bill:{TODAY}",
            "amount": Decimal("100"),
            "reason": "Test rollback",
        },
    )
    with pytest.raises(ValidationError):
        reviews.confirm(lease.pk, actor=actor, token=reviewed["token"] + "x")

    def fail(*args, **kwargs):
        raise RuntimeError("Audit failure")

    monkeypatch.setattr(applications, "audit", fail)
    with pytest.raises(RuntimeError):
        reviews.confirm(lease.pk, actor=actor, token=reviewed["token"])
    assert not FundsApplication.objects.exists()
    assert services.build_ledger(lease).credit == 200


def test_scheduled_debt_survives_moveout_and_settlement_stays_locked(setup):
    actor, lease, _ = opening(setup, "DEBT", "1500")
    confirm_plan(actor, lease)
    lease.status = "ENDED"
    lease.save()
    assert services.build_ledger(lease).future_repayments == 1000
    from apps.leases.services import settle_account

    with pytest.raises(ValidationError):
        settle_account(lease, actor=actor)
    lease.account_status = "SETTLED"
    lease.settled_at = timezone.now()
    lease.save()
    with pytest.raises(ValidationError):
        reviews.prepare(lease, actor=actor, action="plan", data=plan_data())


def test_new_starting_debt_requires_reviewed_dates(setup):
    actor, lease = setup
    with pytest.raises(ValidationError):
        cutover.prepare(
            lease, actor=actor, kind="DEBT", amount=Decimal("500"), note="No dates supplied"
        )
    data = plan_data()
    data.pop("correction_direction")
    data.pop("correction_amount")
    data.pop("reason")
    reviewed = cutover.prepare(
        lease, actor=actor, kind="DEBT", amount=Decimal("11500"), note="Stated debt", **data
    )
    assert not Charge.objects.exists()
    cutover.confirm(lease.pk, actor=actor, token=reviewed["token"])
    assert RepaymentPlan.objects.get(lease=lease).installments.count() == 23


def test_plain_form_review_back_and_tenant_privacy(setup, client):
    actor, lease, _ = opening(setup, "DEBT", "11500")
    client.force_login(actor)
    path = reverse("ledger:repayment-plan", args=[lease.pk])
    values = {key: value if value is not None else "" for key, value in plan_data().items()}
    values["action"] = "review"
    result = client.post(path, values)
    assert result.status_code == 200
    assert b"Confirm starting-debt payment dates" in result.content
    assert TODAY.strftime("%b").encode() in result.content
    assert not RepaymentPlan.objects.exists()
    token = result.context["review"]["token"]
    assert client.post(path, {"action": "confirm", "review_token": token}).status_code == 302
    assert RepaymentPlan.objects.count() == 1
    for route in (
        reverse("ledger:lease-ledger", args=[lease.pk]),
        reverse("leases:lease-detail", args=[lease.pk]),
    ):
        assert client.get(route).status_code == 200
    from apps.leases.models import LeaseTenant

    tenant = make_tenant(username="repayment-viewer")
    LeaseTenant.objects.create(lease=lease, tenant=tenant, is_primary=True)
    client.force_login(tenant)
    page = client.get(reverse("payments:home"))
    assert page.status_code == 200
    assert b"Repay starting debt monthly alongside normal rent." in page.content
    assert b"Synthetic phone agreement" not in page.content
    assert b"Owner-authorized synthetic rehearsal" not in page.content
    assert b"Correct starting debt" not in page.content
    assert client.get(path).status_code == 403


def test_historical_backfill_conserves_coverage_and_original_money(setup):
    from importlib import import_module
    from types import SimpleNamespace

    from django.apps import apps
    from django.db import connection

    from tests.factories import make_payment

    _, lease = setup
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    make_payment(lease, amount=Decimal("1200"), payment_date=TODAY)
    before = services.build_ledger(lease)
    snapshot = (before.balance_due, before.due_now, before.credit)
    counts = (Charge.objects.count(), lease.payments.count())
    migration = import_module("apps.ledger.migrations.0008_preserve_legacy_applications")
    migration.preserve(apps, SimpleNamespace(connection=connection))
    after = services.build_ledger(lease)
    assert (after.balance_due, after.due_now, after.credit) == snapshot
    assert counts == (Charge.objects.count(), lease.payments.count())
    assert FundsApplication.objects.get(lease=lease).legacy_derived


def test_correction_review_release_matches_out_of_order_early_applications(setup):
    actor, lease, _ = opening(setup, "DEBT", "1500")
    first = (TODAY.replace(day=1) + dt.timedelta(days=32)).replace(day=5)
    plan = confirm_plan(actor, lease, first_due=first)
    payment = services.record_payment(
        lease, amount=Decimal("800"), payment_date=TODAY, method="CHECK", actor=actor
    )
    for item in (plan.installments.last(), plan.installments.first()):
        proposal = reviews.prepare(
            lease,
            actor=actor,
            action="apply",
            data={
                "source": f"payment:{payment.pk}",
                "target": f"installment:{item.key}",
                "amount": Decimal("400"),
                "reason": "Explicit early repayment",
            },
        )
        reviews.confirm(lease.pk, actor=actor, token=proposal["token"])
    proposal = reviews.prepare(
        lease,
        actor=actor,
        action="plan",
        data=plan_data(
            first_due=first, correction_direction="DECREASE", correction_amount=Decimal("1000")
        ),
    )
    assert Decimal(proposal["plan"]["coverage_released"]) == 400
    reviews.confirm(lease.pk, actor=actor, token=proposal["token"])
    ledger = services.build_ledger(lease)
    assert (ledger.credit, ledger.unpaid_charges, ledger.balance_due) == (400, 100, -300)


def test_replan_does_not_push_every_payment_beyond_early_paid_future_item(setup):
    actor, lease, _ = opening(setup, "DEBT", "1500")
    first = (TODAY.replace(day=1) + dt.timedelta(days=32)).replace(day=5)
    plan = confirm_plan(actor, lease, first_due=first)
    payment = services.record_payment(
        lease, amount=Decimal("400"), payment_date=TODAY, method="CHECK", actor=actor
    )
    item = plan.installments.last()
    proposal = reviews.prepare(
        lease,
        actor=actor,
        action="apply",
        data={
            "source": f"payment:{payment.pk}",
            "target": f"installment:{item.key}",
            "amount": Decimal("400"),
            "reason": "Explicit early repayment",
        },
    )
    reviews.confirm(lease.pk, actor=actor, token=proposal["token"])
    changed = confirm_plan(actor, lease, first_due=first, monthly_amount=Decimal("250"))
    assert changed.installments.first().due_date == first
    assert changed.installments.count() == 5
    assert sum((row.amount for row in changed.installments.all()), Decimal(0)) == 1500
    assert services.build_ledger(lease).credit == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_applications_cannot_spend_credit_twice(setup):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections, connections

    actor, lease, entry = opening(setup)
    make_charge(lease, amount=Decimal("1000"), due_date=TODAY)
    tokens = [
        reviews.prepare(
            lease,
            actor=actor,
            action="apply",
            data={
                "source": f"charge:{entry.charge_id}",
                "target": f"bill:{TODAY}",
                "amount": Decimal("200"),
                "reason": reason,
            },
        )["token"]
        for reason in ("First session", "Second session")
    ]

    def apply(token):
        close_old_connections()
        try:
            reviews.confirm(lease.pk, actor=actor, token=token)
            return "confirmed"
        except ValidationError:
            return "stale"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(apply, tokens)) == ["confirmed", "stale"]
    assert FundsApplication.objects.count() == 1
    assert services.build_ledger(lease).credit == 0
