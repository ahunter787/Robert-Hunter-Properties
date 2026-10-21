"""Reviewed noncash starting records. No historical rent or receipts are invented."""

import datetime as dt
import hashlib
import json
from copy import deepcopy
from decimal import Decimal

from django import forms
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import ADMIN_ROLES, MANAGER_ROLES
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.forms import StyledForm
from apps.documents.models import Document
from apps.leases.models import (
    FinancialCutover,
    Lease,
    LeaseAccountStatus,
    LeaseOpeningRecord,
    LeaseStatus,
)
from apps.ledger.models import Charge, ChargeKind, Direction

SALT = "rhp-starting-account-v1"
STALE = "This account changed or the review expired. Review the starting balance again."


def authorize(actor, *, admin=False):
    roles = ADMIN_ROLES if admin else MANAGER_ROLES
    if not (
        actor.is_authenticated and actor.is_active and (actor.is_superuser or actor.role in roles)
    ):
        raise PermissionDenied


class CutoverForm(StyledForm):
    first_native_date = forms.DateField(
        label="First day of RHP financial records", widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class StartingForm(StyledForm):
    kind = forms.ChoiceField(
        label="Starting account balance",
        choices=[("", "Choose an option"), *LeaseOpeningRecord.Kind.choices],
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    note = forms.CharField(
        label="Cutover note", max_length=1000, widget=forms.Textarea(attrs={"rows": 3})
    )
    evidence = forms.ModelChoiceField(
        queryset=Document.objects.none(), required=False, label="Supporting document (optional)"
    )

    def __init__(self, *args, lease, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.ledger.finance_reviews import RepaymentForm

        for name, field in RepaymentForm.base_fields.items():
            if name.startswith("correction_") or name == "reason":
                continue
            self.fields[name] = deepcopy(field)
            self.fields[name].required = False
            self.fields[name].help_text = "For starting debt only. " + (field.help_text or "")
        self.fields["evidence"].queryset = Document.objects.filter(
            lease=lease, tenant_visible=False
        )

    def clean(self):
        data = super().clean()
        if data.get("kind") == LeaseOpeningRecord.Kind.ZERO:
            if data.get("amount") not in (None, Decimal("0")):
                self.add_error(
                    "amount", "Enter 0 or leave the amount blank for no starting balance."
                )
            data["amount"] = Decimal("0.00")
        elif data.get("kind") and (data.get("amount") is None or data["amount"] <= 0):
            self.add_error("amount", "Enter an amount greater than zero.")
        if data.get("kind") == LeaseOpeningRecord.Kind.DEBT and not self.initial.get(
            "legacy_undated"
        ):
            from apps.ledger.finance_reviews import RepaymentForm

            repayment = RepaymentForm({**data, "reason": data.get("note", "")})
            if not repayment.is_valid():
                for name, errors in repayment.errors.items():
                    for error in errors:
                        self.add_error(name if name in self.fields else None, error)
        return data


def fingerprint(lease):
    return hashlib.sha256(
        json.dumps(
            {
                "lease": [
                    lease.pk,
                    lease.unit_id,
                    lease.start_date,
                    lease.end_date,
                    lease.status,
                    lease.account_status,
                    lease.billing_start_date,
                    lease.financial_ready,
                    lease.updated_at,
                ],
                "charges": list(lease.charges.order_by("pk").values()),
                "payments": list(lease.payments.order_by("pk").values()),
                "rent": list(lease.rent_periods.order_by("pk").values()),
                "nnn": list(lease.nnn_rates.order_by("pk").values()),
                "people": list(lease.lease_tenants.order_by("pk").values()),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def eligible(lease, cutover):
    if (
        lease.status != LeaseStatus.ACTIVE
        or lease.account_status != LeaseAccountStatus.OPEN
        or lease.financial_ready
        or LeaseOpeningRecord.objects.filter(lease=lease).exists()
        or lease.charges.exists()
        or lease.payments.exists()
    ):
        raise ValidationError(
            "This account already has activity or is not eligible for starting records. "
            "Keep its history; do not import a second balance."
        )
    if not lease.start_date < cutover.first_native_date <= lease.end_date:
        raise ValidationError(
            "Starting records are for a lease already underway on the RHP start date."
        )


def prepare(lease, *, actor, kind, amount, note, evidence=None, legacy_undated=False, **repayment):
    authorize(actor)
    lease = Lease.objects.get(pk=lease.pk)
    cutover = FinancialCutover.objects.first()
    if cutover is None:
        raise ValidationError("An administrator must set the RHP financial start date first.")
    eligible(lease, cutover)
    form = StartingForm(
        {
            "kind": kind,
            "amount": amount,
            "note": note,
            "evidence": evidence.pk if evidence else "",
            **repayment,
        },
        lease=lease,
        initial={"legacy_undated": legacy_undated},
    )
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    data = form.cleaned_data
    payload = {
        "actor": actor.pk,
        "lease": lease.pk,
        "cutover": cutover.pk,
        "date": cutover.first_native_date.isoformat(),
        "kind": data["kind"],
        "amount": str(data["amount"]),
        "note": data["note"],
        "evidence": evidence.pk if evidence else None,
        "fingerprint": fingerprint(lease),
    }
    if kind == LeaseOpeningRecord.Kind.DEBT and not legacy_undated:
        from types import SimpleNamespace

        from apps.ledger.finance_reviews import RepaymentForm, schedule

        terms = RepaymentForm({**repayment, "reason": note})
        if not terms.is_valid():
            raise ValidationError(terms.errors.as_text())
        # The same pure schedule projection is used before the opening charge exists.
        proposed = SimpleNamespace(
            charges=[
                SimpleNamespace(
                    charge=SimpleNamespace(
                        pk=None, kind=ChargeKind.OPENING, direction=Direction.INCREASE
                    ),
                    net_amount=data["amount"],
                )
            ],
            repayment_plans=[],
            obligations=[],
        )
        payload["repayment"] = schedule(proposed, terms.cleaned_data)
    return {
        **payload,
        "token": signing.dumps(payload, salt=SALT),
        "date": cutover.first_native_date,
    }


@transaction.atomic
def confirm(lease_id, *, token, actor):
    authorize(actor)
    try:
        data = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError(STALE) from exc
    if data.get("actor") != actor.pk or data.get("lease") != lease_id:
        raise ValidationError(STALE)
    lease = Lease.objects.select_for_update().get(pk=lease_id)
    key = hashlib.sha256(token.encode()).hexdigest()
    previous = LeaseOpeningRecord.objects.filter(review_key=key, lease=lease).first()
    if previous:
        return previous
    cutover = FinancialCutover.objects.select_for_update().get(pk=data["cutover"])
    eligible(lease, cutover)
    if data["date"] != cutover.first_native_date.isoformat() or data["fingerprint"] != fingerprint(
        lease
    ):
        raise ValidationError(STALE)
    evidence = None
    if data["evidence"]:
        evidence = (
            Document.objects.select_for_update()
            .filter(pk=data["evidence"], lease=lease, tenant_visible=False)
            .first()
        )
        if evidence is None:
            raise ValidationError("The supporting document changed. Review again.")
    amount = Decimal(data["amount"])
    from apps.ledger.applications import initialize

    initialize(lease)
    charge = None
    if data["kind"] != LeaseOpeningRecord.Kind.ZERO:
        charge = Charge.objects.create(
            lease=lease,
            kind=ChargeKind.OPENING,
            direction=Direction.DECREASE
            if data["kind"] == LeaseOpeningRecord.Kind.CREDIT
            else Direction.INCREASE,
            amount=amount,
            due_date=cutover.first_native_date,
            aging_unknown=True,
            description="Balance brought forward — manager-entered; historical aging unknown",
            created_by=actor,
        )
    opening = LeaseOpeningRecord.objects.create(
        lease=lease,
        cutover=cutover,
        kind=data["kind"],
        amount=amount,
        note=data["note"],
        charge=charge,
        evidence=evidence,
        created_by=actor,
        review_key=key,
    )
    if data.get("repayment"):
        from apps.ledger.models import RepaymentInstallment, RepaymentPlan

        proposal = data["repayment"]
        terms = proposal["data"]
        plan = RepaymentPlan.objects.create(
            lease=lease,
            charge=charge,
            first_due=terms["first_due"],
            monthly_amount=terms["monthly_amount"] if terms["mode"] == "monthly" else None,
            agreed_on=terms["agreed_on"],
            agreement_source=terms["agreement_source"],
            explanation=terms["explanation"],
            reason=terms["reason"],
            created_by=actor,
            review_key=key,
        )
        for item in proposal["items"]:
            RepaymentInstallment.objects.create(
                plan=plan, key=item["key"], due_date=item["date"], amount=Decimal(item["amount"])
            )
    lease.financial_ready = True
    lease.billing_start_date = cutover.first_native_date
    lease.save(update_fields=["financial_ready", "billing_start_date", "updated_at"])
    record(
        actor,
        AuditAction.LEASE_ONBOARDED,
        obj=opening,
        lease=lease,
        summary=f"Starting account recorded: {opening.get_kind_display()} ({amount})",
        workflow="stated_cutover",
        amount=str(amount),
        kind=opening.kind,
        cutover_date=data["date"],
        note=data["note"],
        evidence=data["evidence"],
        verified=False,
    )
    return opening


def prepare_date(*, actor, first_native_date, note):
    authorize(actor, admin=True)
    form = CutoverForm({"first_native_date": first_native_date, "note": note})
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    if FinancialCutover.objects.exists():
        raise ValidationError("The RHP financial start date has already been set.")
    return signing.dumps(
        {
            "actor": actor.pk,
            "date": first_native_date.isoformat(),
            "note": form.cleaned_data["note"],
        },
        salt=SALT + "-date",
    )


@transaction.atomic
def confirm_date(*, actor, token):
    authorize(actor, admin=True)
    try:
        data = signing.loads(token, salt=SALT + "-date", max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError(STALE) from exc
    if data.get("actor") != actor.pk:
        raise ValidationError(STALE)
    existing = FinancialCutover.objects.first()
    if existing:
        if (
            existing.created_by_id == actor.pk
            and existing.first_native_date.isoformat() == data["date"]
            and existing.note == data["note"]
        ):
            return existing
        raise ValidationError(STALE)
    cutover = FinancialCutover.objects.create(
        first_native_date=dt.date.fromisoformat(data["date"]), note=data["note"], created_by=actor
    )
    record(
        actor,
        AuditAction.LEASE_ONBOARDED,
        obj=cutover,
        summary="RHP financial start date confirmed",
        workflow="financial_cutover",
        date=data["date"],
    )
    return cutover
