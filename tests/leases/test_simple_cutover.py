"""Stated starting entries are not reconstructed bills or cash receipts."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.leases import cutover
from apps.leases.models import FinancialCutover, LeaseOpeningRecord
from apps.ledger import services
from apps.ledger.models import Charge, Direction, Payment
from apps.ledger.presentation import bill_history
from tests.factories import make_admin, make_charge, make_lease, make_manager, make_tenant

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def setup():
    actor = make_admin()
    date = TODAY.replace(day=1)
    cutover.confirm_date(
        actor=actor,
        token=cutover.prepare_date(actor=actor, first_native_date=date, note="Synthetic rehearsal"),
    )
    lease = make_lease(
        start_date=date - dt.timedelta(days=400),
        end_date=date + dt.timedelta(days=400),
        billing_start_date=None,
    )
    return actor, lease, date


def review(actor, lease, kind="DEBT", amount="200"):
    return cutover.prepare(
        lease,
        actor=actor,
        kind=kind,
        amount=Decimal(amount),
        note="Manager stated; no source history available",
        legacy_undated=True,
    )


@pytest.mark.parametrize(
    "kind,amount,balance", [("DEBT", "200", "200"), ("CREDIT", "200", "-200"), ("ZERO", "0", "0")]
)
def test_starting_states_are_not_receipts(setup, kind, amount, balance):
    actor, lease, date = setup
    prepared = review(actor, lease, kind, amount)
    assert not LeaseOpeningRecord.objects.exists()
    assert not Charge.objects.exists()
    entry = cutover.confirm(lease.pk, token=prepared["token"], actor=actor)
    lease.refresh_from_db()
    ledger = services.build_ledger(lease)
    assert ledger.balance_due == Decimal(balance)
    assert not Payment.objects.exists()
    assert lease.start_date < date
    assert lease.financial_ready and not lease.needs_starting_account
    assert ledger.arrears == 0
    assert ledger.due_now == (Decimal(amount) if kind == "DEBT" else 0)
    assert ledger.arrears_oldest is None
    assert entry.note.startswith("Manager stated")
    assert entry.evidence_id is None
    assert cutover.confirm(lease.pk, token=prepared["token"], actor=actor).pk == entry.pk
    assert LeaseOpeningRecord.objects.count() == 1
    assert Charge.objects.count() == (0 if kind == "ZERO" else 1)
    if kind != "ZERO":
        assert bill_history(ledger)[0].is_opening


def test_the_opening_charge_is_audited_as_a_charge(setup):
    """ADR-028 D4: the starting account is the one legitimate opening-charge write path."""
    actor, lease, _date = setup
    cutover.confirm(lease.pk, token=review(actor, lease, "DEBT", "200")["token"], actor=actor)

    events = AuditEvent.objects.filter(lease=lease, action="CHARGE_CREATED")
    assert events.count() == 1
    assert events.get().metadata["source"] == "starting account"


def test_credit_is_held_against_new_rent_without_becoming_income(setup):
    actor, lease, _date = setup
    cutover.confirm(lease.pk, token=review(actor, lease, "CREDIT", "200")["token"], actor=actor)
    lease.refresh_from_db()
    make_charge(lease, amount=Decimal("500"), due_date=TODAY)
    ledger = services.build_ledger(lease)
    assert ledger.balance_due == 300
    assert ledger.due_now == 500
    assert ledger.credit == 200
    assert ledger.effective_payments == []
    assert sum((p.amount for p in ledger.effective_payments), Decimal(0)) == 0


def test_opening_credit_corrections_keep_original(setup):
    actor, lease, _ = setup
    entry = cutover.confirm(
        lease.pk, token=review(actor, lease, "CREDIT", "200")["token"], actor=actor
    )
    services.create_adjustment(
        entry.charge,
        direction=Direction.INCREASE,
        amount=Decimal("50"),
        reason="Correct credit",
        actor=actor,
    )
    lease.refresh_from_db()
    assert services.build_ledger(lease).balance_due == -150
    entry.charge.refresh_from_db()
    assert entry.charge.amount == 200


@pytest.mark.parametrize(
    "kind,amount", [("", "0"), ("DEBT", ""), ("CREDIT", "-5"), ("ZERO", "100"), ("DEBT", "0")]
)
def test_explicit_choice_and_valid_amount_required(setup, kind, amount):
    _, lease, _ = setup
    assert not cutover.StartingForm(
        {"kind": kind, "amount": amount, "note": "Test"}, lease=lease
    ).is_valid()


def test_stale_review_and_wrong_actor_rejected(setup):
    actor, lease, _ = setup
    token = review(actor, lease)["token"]
    with pytest.raises(ValidationError):
        cutover.confirm(lease.pk, token=token, actor=make_manager())
    lease.monthly_rent += 1
    lease.save()
    with pytest.raises(ValidationError):
        cutover.confirm(lease.pk, token=token, actor=actor)
    assert not LeaseOpeningRecord.objects.exists()


def test_tampered_and_expired_review(setup, monkeypatch):
    actor, lease, _ = setup
    token = review(actor, lease)["token"]
    with pytest.raises(ValidationError):
        cutover.confirm(lease.pk, token=token + "x", actor=actor)
    monkeypatch.setattr(signing.time, "time", lambda: 9999999999)
    with pytest.raises(ValidationError):
        cutover.confirm(lease.pk, token=token, actor=actor)


def test_existing_entries_are_not_imported_twice(setup):
    actor, lease, _ = setup
    make_charge(lease)
    with pytest.raises(ValidationError, match="already has activity"):
        review(actor, lease)


def test_audit_failure_rolls_back_all_writes(setup, monkeypatch):
    actor, lease, _ = setup
    token = review(actor, lease)["token"]

    def fail(*args, **kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(cutover, "record", fail)
    with pytest.raises(RuntimeError):
        cutover.confirm(lease.pk, token=token, actor=actor)
    assert not Charge.objects.exists()
    assert not LeaseOpeningRecord.objects.exists()
    lease.refresh_from_db()
    assert not lease.financial_ready


def test_immutable_records(setup):
    actor, lease, _ = setup
    entry = cutover.confirm(lease.pk, token=review(actor, lease)["token"], actor=actor)
    for obj in (entry, FinancialCutover.objects.get()):
        with pytest.raises(ValidationError):
            obj.save()
        with pytest.raises(ValidationError):
            obj.delete()
        with pytest.raises(ValidationError):
            type(obj).objects.filter(pk=obj.pk).update(created_by=actor)


def test_worker_and_tenant_denied(setup, client):
    _, lease, _ = setup
    tenant = make_tenant()
    client.force_login(tenant)
    assert client.get(reverse("leases:onboard", args=[lease.pk])).status_code == 403
    assert client.get(reverse("leases:financial-start")).status_code == 403
    with pytest.raises(PermissionDenied):
        review(tenant, lease)


def test_manager_can_review_but_not_set_installation_date(setup, client):
    _, lease, _ = setup
    manager = make_manager()
    client.force_login(manager)
    assert client.get(reverse("leases:financial-start")).status_code == 403
    url = reverse("leases:onboard", args=[lease.pk])
    result = client.post(
        url,
        {
            "action": "review",
            "kind": "DEBT",
            "amount": "200",
            "note": "Stated by manager",
            "mode": "single",
            "first_due": str(TODAY),
            "agreed_on": str(TODAY),
            "agreement_source": "Synthetic phone agreement",
            "explanation": "Starting debt due on the agreed date.",
        },
    )
    assert result.status_code == 200
    assert b"Confirm starting account" in result.content
    assert not Charge.objects.exists()
    token = result.context["review"]["token"]
    assert client.post(url, {"action": "confirm", "review_token": token}).status_code == 302
    assert AuditEvent.objects.filter(metadata__workflow="stated_cutover").exists()


def test_native_generation_starts_at_cutover_and_never_future(setup):
    actor, lease, date = setup
    cutover.confirm(lease.pk, token=review(actor, lease, "ZERO", "0")["token"], actor=actor)
    lease.refresh_from_db()
    services.generate_charges(lease, through=lease.end_date, actor=actor)
    assert all(date <= c.due_date <= TODAY for c in lease.charges.all())
    assert lease.charges.count() <= 1


def test_settled_and_ended_accounts_reject_opening(setup):
    from apps.leases.models import LeaseAccountStatus, LeaseStatus

    actor, lease, _ = setup
    lease.status = LeaseStatus.ENDED
    lease.save()
    with pytest.raises(ValidationError):
        review(actor, lease)
    lease.account_status = LeaseAccountStatus.SETTLED
    lease.settled_at = timezone.now()
    lease.save()
    with pytest.raises(ValidationError):
        review(actor, lease)


def test_inactive_actor_cannot_confirm(setup):
    actor, lease, _ = setup
    token = review(actor, lease)["token"]
    actor.is_active = False
    with pytest.raises(PermissionDenied):
        cutover.confirm(lease.pk, token=token, actor=actor)


def test_forged_lease_identifier_rejects_review(setup):
    actor, lease, _ = setup
    other = make_lease()
    with pytest.raises(ValidationError):
        cutover.confirm(other.pk, token=review(actor, lease)["token"], actor=actor)
    assert not LeaseOpeningRecord.objects.exists()


def test_document_scope_and_visibility_revalidated(setup):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.services import upload_document

    actor, lease, _ = setup
    other = make_lease()
    doc = upload_document(
        title="Private source",
        category="OTHER",
        lease=other,
        file=SimpleUploadedFile("note.txt", b"private evidence"),
        actor=actor,
    )
    with pytest.raises(ValidationError):
        cutover.prepare(
            lease,
            actor=actor,
            kind="DEBT",
            amount=Decimal(200),
            note="Test",
            evidence=doc,
            legacy_undated=True,
        )
    doc.lease = lease
    doc.save()
    token = cutover.prepare(
        lease,
        actor=actor,
        kind="DEBT",
        amount=Decimal(200),
        note="Test",
        evidence=doc,
        legacy_undated=True,
    )["token"]
    doc.tenant_visible = True
    doc.save()
    with pytest.raises(ValidationError, match="document changed"):
        cutover.confirm(lease.pk, token=token, actor=actor)
    assert not Charge.objects.exists()


def test_tenant_statement_does_not_expose_note_or_evidence(setup, client):
    from apps.leases.models import LeaseTenant

    actor, lease, _ = setup
    tenant = make_tenant()
    LeaseTenant.objects.create(lease=lease, tenant=tenant, is_primary=True)
    token = review(actor, lease, "CREDIT", "200")["token"]
    cutover.confirm(lease.pk, token=token, actor=actor)
    client.force_login(tenant)
    response = client.get("/payments/")
    assert response.status_code == 200
    assert b"Balance brought forward" in response.content
    assert b"money-received" in response.content
    assert b"Manager stated; no source history available" not in response.content
    assert b"Adjust</a>" not in response.content
    client.force_login(make_tenant(username="unrelated"))
    assert b"Balance brought forward" not in client.get("/payments/").content


def test_opening_entries_are_not_new_monthly_charges_or_receipts(setup):
    from apps.dashboard.services import project

    actor, lease, _ = setup
    cutover.confirm(lease.pk, token=review(actor, lease)["token"], actor=actor)
    result = project(actor)
    assert result["metrics"]["month-charges"].value == 0
    assert result["metrics"]["month-payments"].value == 0


def test_receipts_require_setup_and_never_backdate_before_cutover(setup):
    actor, lease, date = setup
    with pytest.raises(ValidationError, match="starting account"):
        services.record_payment(
            lease, amount=Decimal(50), payment_date=TODAY, method="CHECK", actor=actor
        )
    cutover.confirm(lease.pk, token=review(actor, lease)["token"], actor=actor)
    # The service must re-read readiness even when a caller retains an old Lease instance.
    services.record_payment(
        lease, amount=Decimal(50), payment_date=TODAY, method="CHECK", actor=actor
    )
    assert services.build_ledger(lease).due_now == 150
    with pytest.raises(ValidationError, match="Earlier payments"):
        services.record_payment(
            lease,
            amount=Decimal(50),
            payment_date=date - dt.timedelta(days=1),
            method="CHECK",
            actor=actor,
        )


def test_linked_evidence_cannot_be_removed_before_protection_check(setup):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.services import remove_document, upload_document

    actor, lease, _ = setup
    doc = upload_document(
        title="Source",
        category="OTHER",
        lease=lease,
        file=SimpleUploadedFile("source.txt", b"retained evidence"),
        actor=actor,
    )
    token = cutover.prepare(
        lease,
        actor=actor,
        kind="DEBT",
        amount=Decimal(200),
        note="Stated",
        evidence=doc,
        legacy_undated=True,
    )["token"]
    cutover.confirm(lease.pk, token=token, actor=actor)
    with pytest.raises(ValidationError, match="must be retained"):
        remove_document(doc, note="Filed in error", actor=actor)
    assert doc.file.storage.exists(doc.file.name)
