"""The rent ledger: charges, payments, and the rules that keep them honest.

Phase 4. Two things are deliberately absent here:

* **No balance column.** A balance is what the entries say it is; a wrong balance
  is a wrong entry, corrected by another entry, never by editing a number
  (ADR-008).
* **No stored charge status.** "Paid", "partly paid" and "overdue" are functions
  of the entries and the calendar, so they are derived — the opposite of
  ``Lease.status``, which is a fact somebody decided.

Entries are append-only. ``save()`` refuses to change a financial field and
``delete()`` refuses outright; a mistake is corrected with a reversal or an
adjustment row, both of which name the entry they correct.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.leases.models import Lease, LeaseStatus

#: What an amount is never allowed to be.
MINIMUM_AMOUNT = Decimal("0.01")


class ChargeKind(models.TextChoices):
    RENT = "RENT", "Rent"
    NNN = "NNN", "NNN"
    MANUAL = "MANUAL", "Manual charge"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class Direction(models.TextChoices):
    """Which way an entry moves the balance."""

    INCREASE = "INCREASE", "Increases what is owed"
    DECREASE = "DECREASE", "Reduces what is owed"


class ChargeState(models.TextChoices):
    """Derived, never stored: see ``apps.ledger.services.build_ledger``."""

    UNPAID = "UNPAID", "Unpaid"
    PARTIAL = "PARTIAL", "Partly paid"
    PENDING = "PENDING", "Payment pending"
    PAID = "PAID", "Paid"
    OVERDUE = "OVERDUE", "Overdue"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class PaymentKind(models.TextChoices):
    RECEIVED = "RECEIVED", "Payment received"
    REVERSAL = "REVERSAL", "Reversal"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CLEARED = "CLEARED", "Cleared"
    VOID = "VOID", "Void"


class PaymentMethod(models.TextChoices):
    ACH = "ACH", "ACH transfer"
    CARD = "CARD", "Card"
    CHECK = "CHECK", "Check"
    CASH = "CASH", "Cash"
    OTHER = "OTHER", "Other"


def _refuse_on_a_draft(entry):
    """A draft lease has no ledger: its rent and term can still change.

    Takes the entry rather than the lease because a model form's instance has no
    lease until the view supplies one, and reading it would raise.
    """
    if entry.lease_id is None:
        return
    if entry.lease.status == LeaseStatus.DRAFT:
        raise ValidationError(
            "A draft lease has no ledger yet: its terms can still change. Activate the lease first."
        )


class ChargeQuerySet(models.QuerySet):
    def for_lease(self, lease):
        return self.filter(lease=lease)

    def rent(self):
        return self.filter(kind=ChargeKind.RENT)

    def positive(self):
        """Charges that add to the balance — the ones a payment can settle."""
        return self.exclude(direction=Direction.DECREASE)


class Charge(models.Model):
    """Something a tenancy was charged for."""

    #: Fields frozen once written. ``kind`` of ADJUSTMENT entries is included
    #: because changing it would change history's meaning.
    FROZEN_FIELDS = (
        "lease_id",
        "kind",
        "direction",
        "description",
        "amount",
        "due_date",
        "adjusts_id",
    )

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="charges")
    kind = models.CharField(max_length=16, choices=ChargeKind.choices, default=ChargeKind.MANUAL)
    direction = models.CharField(
        max_length=8, choices=Direction.choices, default=Direction.INCREASE
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(MINIMUM_AMOUNT)]
    )
    due_date = models.DateField()
    #: The entry this one corrects. Required when an adjustment reduces a charge,
    #: because "which charge?" is the first question anyone will ask.
    adjusts = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adjustments",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Why this entry exists. Required for adjustments.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ChargeQuerySet.as_manager()

    class Meta:
        ordering = ("due_date", "pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=MINIMUM_AMOUNT),
                name="charge_amount_is_at_least_a_cent",
            ),
            # Rent and manual charges only ever add to what is owed. An
            # adjustment is the one entry that may reduce it.
            models.CheckConstraint(
                condition=models.Q(kind=ChargeKind.ADJUSTMENT)
                | models.Q(direction=Direction.INCREASE),
                name="only_adjustments_reduce_a_charge",
            ),
            # Makes rent generation idempotent in the database rather than in the
            # hope that nobody clicks twice.
            models.UniqueConstraint(
                fields=["lease", "due_date"],
                condition=models.Q(kind=ChargeKind.RENT),
                name="one_rent_charge_per_month",
            ),
            # The same rule for a triple-net lease's NNN amount (E1).
            models.UniqueConstraint(
                fields=["lease", "due_date"],
                condition=models.Q(kind=ChargeKind.NNN),
                name="one_nnn_charge_per_month",
            ),
        ]
        indexes = [
            models.Index(fields=["lease", "due_date"], name="charge_lease_due"),
            models.Index(fields=["kind", "due_date"], name="charge_kind_due"),
        ]

    def __str__(self) -> str:
        return f"{self.description} {self.amount} due {self.due_date}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values(*self.FROZEN_FIELDS).first()
            if stored is not None:
                changed = [
                    field for field in self.FROZEN_FIELDS if stored[field] != getattr(self, field)
                ]
                if changed:
                    raise ValidationError(
                        "Ledger entries are never edited. Reverse it, or add an adjustment "
                        "that says what was wrong."
                    )
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Charges are never deleted. An adjustment of the right amount is the correction."
        )

    def clean(self):
        super().clean()
        _refuse_on_a_draft(self)
        if self.kind == ChargeKind.ADJUSTMENT:
            if not self.reason:
                raise ValidationError({"reason": "An adjustment needs a reason."})
            if self.direction == Direction.DECREASE and self.adjusts is None:
                raise ValidationError({"adjusts": "Say which charge this adjustment reduces."})
        elif self.adjusts is not None:
            raise ValidationError({"adjusts": "Only an adjustment corrects another charge."})
        if self.amount is not None and self.amount < MINIMUM_AMOUNT:
            raise ValidationError({"amount": "An amount must be at least one cent."})

    @property
    def balance_effect(self) -> Decimal:
        """What this entry does to the balance: positive means more is owed."""
        if self.direction == Direction.DECREASE:
            return -self.amount
        return self.amount

    @property
    def is_reduction(self) -> bool:
        return self.direction == Direction.DECREASE


class PaymentQuerySet(models.QuerySet):
    def for_lease(self, lease):
        return self.filter(lease=lease)

    def effective(self):
        """Money that counts: cleared, received, and not since reversed."""
        reversed_ids = self.model.objects.filter(reverses__isnull=False).values("reverses_id")
        return self.filter(kind=PaymentKind.RECEIVED, status=PaymentStatus.CLEARED).exclude(
            pk__in=reversed_ids
        )


class Payment(models.Model):
    """Money in, or the reversal of money in."""

    FROZEN_FIELDS = (
        "lease_id",
        "kind",
        "amount",
        "payment_date",
        "method",
        "external_reference",
        "reverses_id",
    )

    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(
        max_length=16, choices=PaymentKind.choices, default=PaymentKind.RECEIVED
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(MINIMUM_AMOUNT)]
    )
    payment_date = models.DateField()
    method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.ACH
    )
    status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.CLEARED
    )
    external_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="The bank or processor reference, or a check number.",
    )
    notes = models.TextField(blank=True)
    #: The payment this row reverses. OneToOne: a payment is reversed once.
    reverses = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversal",
    )
    reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ("payment_date", "pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=MINIMUM_AMOUNT),
                name="payment_amount_is_at_least_a_cent",
            ),
            models.CheckConstraint(
                condition=models.Q(kind=PaymentKind.RECEIVED, reverses__isnull=True)
                | models.Q(kind=PaymentKind.REVERSAL, reverses__isnull=False),
                name="a_reversal_references_the_payment_it_reverses",
            ),
        ]
        indexes = [
            models.Index(fields=["lease", "payment_date"], name="payment_lease_date"),
            models.Index(fields=["status", "payment_date"], name="payment_status_date"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} on {self.payment_date}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = (
                type(self).objects.filter(pk=self.pk).values(*self.FROZEN_FIELDS, "status").first()
            )
            if stored is not None:
                changed = [
                    field for field in self.FROZEN_FIELDS if stored[field] != getattr(self, field)
                ]
                if changed:
                    raise ValidationError(
                        "Payments are never edited. Reverse it, or record the correction as a "
                        "new payment."
                    )
                # The one permitted change is the pending lifecycle: money that
                # was expected either arrives or turns out never to have existed.
                if stored["status"] != self.status and not (
                    stored["status"] == PaymentStatus.PENDING
                    and self.status in (PaymentStatus.CLEARED, PaymentStatus.VOID)
                ):
                    raise ValidationError(
                        "A payment's status only moves from pending to cleared or void. A "
                        "cleared payment is corrected with a reversal."
                    )
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Payments are never deleted. Reverse it, so the correction is visible."
        )

    def clean(self):
        super().clean()
        _refuse_on_a_draft(self)
        if self.kind == PaymentKind.REVERSAL:
            if self.reverses is None:
                raise ValidationError(
                    {"reverses": "A reversal must say which payment it reverses."}
                )
            if not self.reason:
                raise ValidationError({"reason": "A reversal needs a reason."})
            if self.status != PaymentStatus.CLEARED:
                raise ValidationError(
                    {"status": "A reversal is an accounting fact; it is never pending."}
                )
        elif self.reverses is not None:
            raise ValidationError({"reverses": "Only a reversal references another payment."})
        if self.amount is not None and self.amount < MINIMUM_AMOUNT:
            raise ValidationError({"amount": "An amount must be at least one cent."})

    @property
    def balance_effect(self) -> Decimal:
        """What this entry does to the balance: negative means less is owed."""
        return self.amount if self.kind == PaymentKind.REVERSAL else -self.amount

    @property
    def is_reversal(self) -> bool:
        return self.kind == PaymentKind.REVERSAL

    @property
    def counts_toward_balance(self) -> bool:
        return self.kind == PaymentKind.RECEIVED and self.status == PaymentStatus.CLEARED

    @property
    def is_overdue_candidate(self) -> bool:
        """True when this payment is still expected but its date has passed."""
        return self.status == PaymentStatus.PENDING and self.payment_date < timezone.localdate()

    def is_reversed(self) -> bool:
        """Whether a reversal row exists for this payment.

        A method rather than a property because the ledger page answers it for
        every payment at once; calling this per row would be a query per row.
        """
        if self.pk is None:
            return False
        return type(self).objects.filter(reverses_id=self.pk).exists()
