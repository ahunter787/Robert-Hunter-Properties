"""The general ledger: a chart, sourced immutable journals and their lines.

B1 of RHP property accounting ([ADR-032](../docs/decisions/ADR-032-b1-readiness.md)).
The sub-ledger stays authoritative for "what does this tenancy owe"; the GL is the
double-entry reading of the same kernel events. Nothing here stores a balance.
"""

import builtins
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

ZERO = Decimal("0.00")


class AccountKind(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    EQUITY = "EQUITY", "Equity"
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


class NormalSide(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class ChartAccount(models.Model):
    """One account in RHP's own books; codes follow the readiness chart."""

    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=12, choices=AccountKind.choices)
    normal_side = models.CharField(max_length=6, choices=NormalSide.choices)
    is_system = models.BooleanField(
        default=False,
        help_text="A control/bank/equity account the ledger relies on; it may be renamed but "
        "not deleted once it carries history.",
    )
    is_control = models.BooleanField(
        default=False,
        help_text="Moves only from kernel source events; never from a manual journal.",
    )
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} {self.name}"

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError("A system account cannot be deleted; deactivate it instead.")
        if self.journal_lines.exists():
            raise ValidationError("An account with journal history cannot be deleted.")
        return super().delete(*args, **kwargs)


class AccountMapping(models.Model):
    """The chart account an event key posts to when the event does not name one."""

    event_key = models.CharField(max_length=80, unique=True)
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT, related_name="mappings")
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("event_key",)

    def __str__(self):
        return f"{self.event_key} -> {self.account.code}"


class JournalEntryQuerySet(models.QuerySet):
    def for_property(self, property):
        return self.filter(property=property)


class JournalEntry(models.Model):
    """A balanced, sourced, immutable journal. Corrections are reversing entries."""

    FROZEN_FIELDS = (
        "source_key",
        "event_type",
        "posted_on",
        "property_id",
        "lease_id",
        "memo",
        "reversal_of_id",
    )

    source_key = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=60, db_index=True)
    posted_on = models.DateField()
    property = models.ForeignKey(
        "properties.Property",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="accounting_entries",
    )
    lease = models.ForeignKey(
        "leases.Lease",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="accounting_entries",
    )
    memo = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )

    objects = JournalEntryQuerySet.as_manager()

    class Meta:
        ordering = ("posted_on", "pk")
        indexes = [models.Index(fields=["posted_on", "event_type"], name="journal_date_event")]

    def __str__(self):
        return f"JE-{self.pk} {self.event_type} {self.posted_on}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values(*self.FROZEN_FIELDS).first()
            if stored is not None:
                changed = [
                    field for field in self.FROZEN_FIELDS if stored[field] != getattr(self, field)
                ]
                if changed:
                    raise ValidationError(
                        "Posted journals are never edited. Reverse the entry and post the "
                        "correction as a new source event."
                    )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Posted journals are never deleted; reverse them instead.")


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(
        ChartAccount, on_delete=models.PROTECT, related_name="journal_lines"
    )
    property = models.ForeignKey(
        "properties.Property",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="accounting_lines",
    )
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    memo = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name="journal_line_nonnegative",
            ),
            models.CheckConstraint(
                condition=(models.Q(debit__gt=0, credit=0) | models.Q(credit__gt=0, debit=0)),
                name="journal_line_one_side",
            ),
        ]
        indexes = [models.Index(fields=["account", "entry"], name="journal_line_account")]

    def __str__(self):
        side = f"Dr {self.debit}" if self.debit else f"Cr {self.credit}"
        return f"{self.account.code} {side}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Journal lines are immutable; post a reversing entry instead.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal lines are immutable; post a reversing entry instead.")


class OpeningBalanceBatch(models.Model):
    """A reviewed opening journal: the balance sheet RHP starts its GL from.

    Values are owner/onboarding facts supplied at go-live. The batch is a durable, immutable
    record of what was posted; corrections are new batches or reversing entries, never edits.
    """

    key = models.UUIDField(unique=True)
    as_of = models.DateField()
    note = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    journal = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="opening_batch"
    )

    class Meta:
        ordering = ("-as_of", "-pk")

    def __str__(self):
        return f"Opening balances {self.as_of}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = (
                type(self).objects.filter(pk=self.pk).values("as_of", "note", "journal_id").first()
            )
            if stored is not None and stored["journal_id"] is not None:
                if any(
                    stored[field] != getattr(self, field)
                    for field in ("as_of", "note", "journal_id")
                ):
                    raise ValidationError("A posted opening batch is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Opening batches are never deleted; reverse the journal instead.")


class OpeningBalanceLine(models.Model):
    batch = models.ForeignKey(OpeningBalanceBatch, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartAccount, on_delete=models.PROTECT)
    property = models.ForeignKey(
        "properties.Property", null=True, blank=True, on_delete=models.PROTECT
    )
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    memo = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name="opening_line_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(debit__gt=0, credit=0) | models.Q(credit__gt=0, debit=0),
                name="opening_line_one_side",
            ),
        ]

    def __str__(self):
        side = f"Dr {self.debit}" if self.debit else f"Cr {self.credit}"
        return f"{self.account.code} {side}"


class VendorBill(models.Model):
    """A vendor's bill: expense recorded now, payable until paid (B2)."""

    property = models.ForeignKey("properties.Property", on_delete=models.PROTECT)
    vendor = models.ForeignKey(
        "maintenance.Vendor", null=True, blank=True, on_delete=models.PROTECT
    )
    expense_account = models.ForeignKey(
        ChartAccount, on_delete=models.PROTECT, related_name="vendor_bills"
    )
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_on = models.DateField()
    due_date = models.DateField()
    note = models.CharField(max_length=500, blank=True)
    journal = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="vendor_bill"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("due_date", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="vendor_bill_positive")
        ]

    def __str__(self):
        return f"{self.description} ({self.amount})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values("journal_id", "amount").first()
            if stored is not None and stored["journal_id"] is not None:
                if stored["amount"] != self.amount:
                    raise ValidationError("A posted vendor bill is immutable.")
        return super().save(*args, **kwargs)

    @builtins.property
    def paid(self):
        return sum((payment.amount for payment in self.payments.all()), ZERO)

    @builtins.property
    def balance(self):
        return (self.amount - self.paid).quantize(ZERO) if self.amount else ZERO

    def delete(self, *args, **kwargs):
        raise ValidationError("Vendor bills are never deleted; correct them with an entry.")


class BillPaymentMethod(models.TextChoices):
    CHECK = "CHECK", "Check"
    ACH = "ACH", "ACH transfer"
    CARD = "CARD", "Card"
    CASH = "CASH", "Cash"
    OTHER = "OTHER", "Other"


class VendorPayment(models.Model):
    """A payment against a vendor bill; cash leaves through undeposited funds until B3."""

    bill = models.ForeignKey(VendorBill, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(
        max_length=8, choices=BillPaymentMethod.choices, default=BillPaymentMethod.ACH
    )
    reference = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=500, blank=True)
    journal = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="bill_payment"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("paid_on", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="vendor_payment_positive")
        ]

    def __str__(self):
        return f"Payment {self.amount} on {self.paid_on}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values("journal_id").first()
            if stored is not None and stored["journal_id"] is not None:
                raise ValidationError("Vendor payments are immutable; add a correcting entry.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Vendor payments are never deleted.")


class BankKind(models.TextChoices):
    OPERATING = "OPERATING", "Operating"
    DEPOSIT = "DEPOSIT", "Deposit/escrow"


class BankAccount(models.Model):
    """A real bank account, entered as data and linked to its chart account."""

    name = models.CharField(max_length=100)
    institution = models.CharField(max_length=120)
    last_four = models.CharField(max_length=4)
    kind = models.CharField(max_length=10, choices=BankKind.choices, default=BankKind.OPERATING)
    chart_account = models.OneToOneField(
        ChartAccount, on_delete=models.PROTECT, related_name="bank_account"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return f"{self.name} · {self.institution} ({self.last_four})"

    def clean(self):
        super().clean()
        if self.chart_account_id and self.chart_account.kind != AccountKind.ASSET:
            raise ValidationError("A bank account must link to an asset chart account.")


class BankMovementKind(models.TextChoices):
    DEPOSIT = "DEPOSIT", "Deposit into bank"
    WITHDRAWAL = "WITHDRAWAL", "Withdrawal from bank"


class BankMovement(models.Model):
    """Money moved between undeposited funds and the bank (the B3 clearing step)."""

    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="movements"
    )
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=BankMovementKind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=200, blank=True)
    memo = models.CharField(max_length=300, blank=True)
    journal = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="bank_movement"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="bank_movement_positive")
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} on {self.date}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values("journal_id").first()
            if stored is not None and stored["journal_id"] is not None:
                raise ValidationError("Bank movements are immutable; record a correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Bank movements are never deleted.")


class BankStatement(models.Model):
    """One imported bank statement period."""

    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="statements"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    imported_at = models.DateTimeField(auto_now_add=True)
    source_name = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-period_end", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="statement_period_ordered",
            ),
            models.UniqueConstraint(
                fields=["bank_account", "period_start", "period_end"],
                name="one_statement_per_bank_period",
            ),
        ]

    def __str__(self):
        return f"{self.bank_account.name} {self.period_start}–{self.period_end}"


class StatementLine(models.Model):
    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name="lines")
    date = models.DateField()
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=200, blank=True)
    matched_journal_line = models.ForeignKey(
        JournalLine, null=True, blank=True, on_delete=models.PROTECT, related_name="statement_lines"
    )

    class Meta:
        ordering = ("date", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=["matched_journal_line"],
                condition=models.Q(matched_journal_line__isnull=False),
                name="journal_line_matched_once",
            )
        ]

    def __str__(self):
        return f"{self.date} {self.description} {self.amount}"


class BankReconciliation(models.Model):
    statement = models.OneToOneField(
        BankStatement, on_delete=models.PROTECT, related_name="reconciliation"
    )
    cleared_total = models.DecimalField(max_digits=12, decimal_places=2)
    adjusted_balance = models.DecimalField(max_digits=12, decimal_places=2)
    difference = models.DecimalField(max_digits=12, decimal_places=2)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    reconciled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reconciliation of {self.statement}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("A reconciliation is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("A reconciliation is never deleted; reopen with a new statement.")


class ExportKind(models.TextChoices):
    JOURNAL_CSV = "JOURNAL_CSV", "Journal CSV"
    JOURNAL_TEXT = "JOURNAL_TEXT", "Plain-text journal"


class ExportBatch(models.Model):
    """A one-way, period-scoped, checksummed accountant export."""

    key = models.UUIDField(unique=True)
    kind = models.CharField(max_length=20, choices=ExportKind.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    row_count = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.get_kind_display()} {self.period_start}–{self.period_end}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Export batches are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Export batches are retained for audit.")


class OwnerTransactionKind(models.TextChoices):
    CONTRIBUTION = "CONTRIBUTION", "Owner contribution"
    DRAW = "DRAW", "Owner draw"


class OwnerTransaction(models.Model):
    """Owner money in or out of the business, through a bank account."""

    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="owner_transactions"
    )
    kind = models.CharField(max_length=20, choices=OwnerTransactionKind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    journal = models.OneToOneField(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owner_transaction",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="owner_transaction_positive"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} on {self.date}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values("journal_id").first()
            if stored is not None and stored["journal_id"] is not None:
                raise ValidationError("Owner transactions are immutable; add a correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Owner transactions are never deleted.")
