"""Signed plain-form reviews for held credit and opening-debt agreements."""

import datetime as dt
import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.dates import due_date_in
from apps.common.forms import StyledForm
from apps.leases.cutover import fingerprint
from apps.leases.models import Lease
from apps.ledger import applications
from apps.ledger.models import (
    Charge,
    ChargeKind,
    Direction,
    FundsApplication,
    RepaymentInstallment,
    RepaymentPlan,
)
from apps.ledger.services import build_ledger, create_adjustment

ZERO = Decimal("0.00")
SALT = "rhp-finance-application-review-v1"
STALE = "This account changed or the review expired. Review the action again."


def date_label(date):
    return f"{date:%b} {date.day}, {date.year}"


def display_review(review):
    """Human dates only in the display copy; the signed payload stays unchanged."""
    if not review:
        return review
    rendered = deepcopy(review)
    proposal = rendered.get("plan") or rendered.get("repayment")
    if proposal:
        for item in proposal["items"]:
            item["date"] = dt.date.fromisoformat(item["date"])
        proposal["data"]["agreed_on"] = dt.date.fromisoformat(proposal["data"]["agreed_on"])
    return rendered


def state(lease):
    return hashlib.sha256(
        json.dumps(
            {
                "ledger": fingerprint(lease),
                "applications": list(lease.funds_applications.order_by("pk").values()),
                "plans": list(lease.repayment_plans.order_by("pk").values()),
                "items": list(
                    RepaymentInstallment.objects.filter(plan__lease=lease).order_by("pk").values()
                ),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def targets(ledger):
    result = {}
    for row in ledger.obligations:
        if row.left <= ZERO:
            continue
        key = (
            f"installment:{row.key}"
            if row.key
            else (
                f"opening:{row.charge.pk}"
                if row.charge.kind == ChargeKind.OPENING
                else f"bill:{row.date.isoformat()}"
            )
        )
        label = (
            "Repayment"
            if row.key
            else "Starting debt"
            if row.charge.kind == ChargeKind.OPENING
            else "Bill"
        )
        result.setdefault(
            key,
            {
                "label": f"{label} · {date_label(row.date)}",
                "rows": [],
            },
        )["rows"].append(row)
    return result


class CreditForm(StyledForm):
    source = forms.ChoiceField(label="Available credit")
    target = forms.ChoiceField(label="Apply to bill or repayment")
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(max_length=1000, label="Reason")

    def __init__(self, *args, ledger, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = [
            (s["value"], f"{s['label']} · ${s['available']:,.2f} available")
            for s in ledger.credit_sources
        ]
        self.fields["target"].choices = [
            (key, value["label"]) for key, value in targets(ledger).items()
        ]


class RepaymentForm(StyledForm):
    mode = forms.ChoiceField(
        label="How will the starting debt be repaid?",
        choices=[
            ("single", "Pay the full balance by one date"),
            ("monthly", "Monthly repayment plan"),
        ],
    )
    first_due = forms.DateField(
        label="Payment due date / first installment date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    monthly_amount = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Monthly repayment amount (monthly plan only)",
    )
    agreed_on = forms.DateField(
        label="Arrangement confirmed on", widget=forms.DateInput(attrs={"type": "date"})
    )
    agreement_source = forms.CharField(
        max_length=500,
        label="How was the arrangement confirmed?",
        help_text="Staff only. For example: phone conversation or signed agreement.",
    )
    explanation = forms.CharField(
        max_length=1000,
        label="Explanation shown to the tenant",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    reason = forms.CharField(
        max_length=1000, label="Staff reason", widget=forms.Textarea(attrs={"rows": 2})
    )
    correction_direction = forms.ChoiceField(
        required=False,
        choices=[
            ("", "No financial correction"),
            ("DECREASE", "Reduce starting debt"),
            ("INCREASE", "Increase starting debt"),
        ],
    )
    correction_amount = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )

    def clean(self):
        data = super().clean()
        if data.get("mode") == "monthly" and not data.get("monthly_amount"):
            self.add_error("monthly_amount", "Enter the agreed monthly repayment amount.")
        if bool(data.get("correction_direction")) != bool(data.get("correction_amount")):
            self.add_error(
                "correction_amount", "Choose a correction direction and amount together."
            )
        if data.get("agreed_on") and data["agreed_on"] > timezone.localdate():
            self.add_error(
                "agreed_on", "Record an arrangement already confirmed, not a future agreement."
            )
        return data


def schedule(ledger, data):
    line = next(
        (
            line
            for line in ledger.charges
            if line.charge.kind == ChargeKind.OPENING
            and line.charge.direction == Direction.INCREASE
        ),
        None,
    )
    if line is None:
        raise ValidationError("This account has no brought-forward debt to schedule.")
    amount = data.get("correction_amount") or ZERO
    net = line.net_amount + (-amount if data.get("correction_direction") == "DECREASE" else amount)
    old = next((p for p in ledger.repayment_plans if p.charge_id == line.charge.pk), None)
    items = []
    if old:
        # A correction retains dates and changes the tail explicitly in the review.
        old_items = list(old.installments.all())
        kept = (
            old_items
            if data.get("correction_direction")
            else [
                row
                for row in old_items
                if row.due_date < timezone.localdate()
                or any(o.key == row.key and o.paid > ZERO for o in ledger.obligations)
            ]
        )
        for row in kept:
            items.append(
                {"key": str(row.key), "date": row.due_date.isoformat(), "amount": str(row.amount)}
            )
    principal = max(net, ZERO)
    total = sum((Decimal(row["amount"]) for row in items), ZERO)
    if total > principal:
        reduction = total - principal
        for row in reversed(items):
            delta = min(Decimal(row["amount"]), reduction)
            row["amount"] = str(Decimal(row["amount"]) - delta)
            reduction -= delta
        items = [row for row in items if Decimal(row["amount"]) > ZERO]
    left = principal - sum((Decimal(row["amount"]) for row in items), ZERO)
    first = data["first_due"]
    fixed_dates = [dt.date.fromisoformat(row["date"]) for row in items]
    boundary = (
        fixed_dates
        if data.get("correction_direction")
        else [date for date in fixed_dates if date < timezone.localdate()]
    )
    if boundary and first <= max(boundary):
        last = max(boundary)
        month = last.month % 12 + 1
        first = due_date_in(last.year + (last.month == 12), month, data["first_due"].day)
    monthly = data.get("monthly_amount") if data["mode"] == "monthly" else None
    for index in range(1200):
        if left <= ZERO:
            break
        year = first.year + (first.month - 1 + index) // 12
        if year > 9999:
            raise ValidationError("The repayment schedule exceeds the supported calendar range.")
        month = (first.month - 1 + index) % 12 + 1
        portion = min(left, monthly) if monthly else left
        date = due_date_in(year, month, data["first_due"].day)
        if date in fixed_dates:
            continue
        items.append({"key": str(uuid4()), "date": date.isoformat(), "amount": str(portion)})
        left -= portion
    if left > ZERO:
        raise ValidationError(
            "This plan exceeds 1,200 monthly installments. Increase the monthly amount."
        )
    items.sort(key=lambda row: (row["date"], row["key"]))
    capacities = {row["key"]: Decimal(row["amount"]) for row in items}
    released = ZERO
    for application in applications.active(getattr(ledger, "application_history", [])):
        if application.target_id != line.charge.pk:
            continue
        if application.installment_key:
            key = str(application.installment_key)
            retained = min(application.amount, capacities.get(key, ZERO))
            capacities[key] = capacities.get(key, ZERO) - retained
        else:
            retained = ZERO
            for key in capacities:
                portion = min(application.amount - retained, capacities[key])
                capacities[key] -= portion
                retained += portion
        released += application.amount - retained
    return {
        "charge": line.charge.pk,
        "previous": old.pk if old else None,
        "principal": str(net),
        "items": items,
        "coverage_released": str(released),
        "data": {k: str(v) if isinstance(v, (Decimal, dt.date)) else v for k, v in data.items()},
    }


def prepare(lease, *, actor, action, data=None, application=None):
    applications.writable(lease, actor)
    # Preview must not create any financial rows: it reads the applications that exist.
    ledger = build_ledger(lease)
    payload = {
        "actor": actor.pk,
        "lease": lease.pk,
        "action": action,
        "state": state(lease),
        "day": timezone.localdate().isoformat(),
    }
    if action == "apply":
        form = CreditForm(data, ledger=ledger)
        if not form.is_valid():
            raise ValidationError(form.errors.as_text())
        data = form.cleaned_data
        source = next((s for s in ledger.credit_sources if s["value"] == data["source"]), None)
        target = targets(ledger).get(data["target"])
        amount = data["amount"]
        if (
            source is None
            or target is None
            or amount <= ZERO
            or amount > source["available"]
            or amount > sum((r.left for r in target["rows"]), ZERO)
        ):
            raise ValidationError(
                "Choose available credit and an amount no greater than the unpaid obligation."
            )
        payload["data"] = {**data, "amount": str(amount)}
        payload["description"] = (
            f"Apply ${amount:,.2f} from {source['label']} to {target['label']}. "
            "No money is transferred or received."
        )
    elif action == "undo":
        row = next(
            (
                row
                for row in applications.active(ledger.application_history)
                if row.pk == application and row.is_credit
            ),
            None,
        )
        if row is None:
            raise ValidationError("This credit application is not available to undo.")
        if not data or not data.get("reason", "").strip():
            raise ValidationError("Enter a reason for undoing this application.")
        payload.update(
            application=row.pk,
            data=data,
            description=(
                f"Undo credit application of ${row.amount:,.2f}; reopen the "
                "unpaid obligation and release the credit. No refund or transfer."
            ),
        )
    elif action == "plan":
        form = RepaymentForm(data)
        if not form.is_valid():
            raise ValidationError(form.errors.as_text())
        data = form.cleaned_data
        payload["plan"] = schedule(ledger, data)
        payload["description"] = (
            "Confirm payment dates for existing starting debt. "
            "This does not add another charge or record a payment."
        )
    else:
        raise ValidationError("Unknown financial action.")
    return {**payload, "token": signing.dumps(payload, salt=SALT)}


@transaction.atomic
def confirm(lease_id, *, token, actor):
    try:
        data = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValidationError(STALE) from exc
    if data.get("actor") != actor.pk or data.get("lease") != lease_id:
        raise ValidationError(STALE)
    lease = Lease.objects.select_for_update().get(pk=lease_id)
    applications.writable(lease, actor)
    key = hashlib.sha256(token.encode()).hexdigest()
    if (
        RepaymentPlan.objects.filter(review_key=key, lease=lease).exists()
        or lease.funds_applications.filter(review_key=key).exists()
    ):
        return
    if data.get("state") != state(lease) or data.get("day") != timezone.localdate().isoformat():
        raise ValidationError(STALE)
    ledger = build_ledger(lease)
    if data["action"] == "apply":
        values = data["data"]
        # Re-run amount/target checks under the tenancy lock.
        values["amount"] = Decimal(values["amount"])
        prepare(lease, actor=actor, action="apply", data=values)
        source_kind, source_id = values["source"].split(":")
        amount = values["amount"]
        for obligation in sorted(
            targets(ledger)[values["target"]]["rows"], key=lambda row: row.charge.pk
        ):
            portion = min(amount, obligation.left)
            if portion > ZERO:
                FundsApplication.objects.create(
                    lease=lease,
                    target=obligation.charge,
                    installment_key=obligation.key,
                    amount=portion,
                    is_credit=True,
                    created_by=actor,
                    reason=values["reason"],
                    review_key=key,
                    **{f"source_{source_kind}_id": int(source_id)},
                )
                amount -= portion
        summary = f"Credit of ${values['amount']:,.2f} applied; no new receipt"
    elif data["action"] == "undo":
        row = next(
            (
                r
                for r in applications.active(ledger.application_history)
                if r.pk == data["application"] and r.is_credit
            ),
            None,
        )
        if row is None:
            raise ValidationError(STALE)
        applications.release(row, actor=actor, reason=data["data"]["reason"], review_key=key)
        summary = f"Credit application of ${row.amount:,.2f} undone; no refund"
    else:
        proposal = data["plan"]
        values = proposal["data"]
        charge = Charge.objects.get(pk=proposal["charge"], lease=lease)
        if values.get("correction_direction"):
            create_adjustment(
                charge,
                direction=values["correction_direction"],
                amount=Decimal(values["correction_amount"]),
                reason=values["reason"],
                actor=actor,
                reviewed_repayment=True,
            )
        plan = RepaymentPlan.objects.create(
            lease=lease,
            charge=charge,
            previous_id=proposal["previous"],
            first_due=values["first_due"],
            monthly_amount=values["monthly_amount"] if values["mode"] == "monthly" else None,
            agreed_on=values["agreed_on"],
            agreement_source=values["agreement_source"],
            explanation=values["explanation"],
            reason=values["reason"],
            created_by=actor,
            review_key=key,
        )
        for item in proposal["items"]:
            RepaymentInstallment.objects.create(
                plan=plan, key=item["key"], due_date=item["date"], amount=Decimal(item["amount"])
            )
        # Retain application identity where possible; explicitly release invalid coverage.
        items = list(plan.installments.all())
        used = {}
        for row in applications.active(list(lease.funds_applications.order_by("pk"))):
            if row.target_id != charge.pk:
                continue
            matching = next((item for item in items if item.key == row.installment_key), None)
            if matching and row.amount + used.get(matching.key, ZERO) <= matching.amount:
                used[matching.key] = used.get(matching.key, ZERO) + row.amount
                continue
            applications.release(
                row, actor=actor, reason="Reviewed repayment schedule replacement", review_key=key
            )
            if matching:
                portion = min(row.amount, matching.amount - used.get(matching.key, ZERO))
                if portion > ZERO:
                    FundsApplication.objects.create(
                        lease=lease,
                        source_payment_id=row.source_payment_id,
                        source_charge_id=row.source_charge_id,
                        source_deposit_id=row.source_deposit_id,
                        target=charge,
                        installment_key=matching.key,
                        amount=portion,
                        is_credit=row.is_credit,
                        created_by=actor,
                        reason="Coverage retained after reviewed correction",
                        review_key=key,
                    )
                    used[matching.key] = used.get(matching.key, ZERO) + portion
            # Existing unkeyed legacy coverage is preserved across the initial schedule.
            if row.installment_key is None:
                remaining = row.amount
                for item in items:
                    portion = min(remaining, item.amount - used.get(item.key, ZERO))
                    if portion > ZERO:
                        FundsApplication.objects.create(
                            lease=lease,
                            source_payment_id=row.source_payment_id,
                            source_charge_id=row.source_charge_id,
                            target=charge,
                            installment_key=item.key,
                            amount=portion,
                            is_credit=row.is_credit,
                            created_by=actor,
                            reason="Existing coverage carried into reviewed schedule",
                            review_key=key,
                        )
                        used[item.key] = used.get(item.key, ZERO) + portion
                        remaining -= portion
        summary = "Starting-debt repayment schedule confirmed; no new charge"
    applications.audit(lease, actor, summary, review_key=key)
