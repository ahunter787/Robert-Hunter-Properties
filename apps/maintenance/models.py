"""Physical work, explicitly scoped conversations, and append-only repair costs."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Status(models.TextChoices):
    OPEN = "OPEN", "Open"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    WAITING = "WAITING", "Waiting"
    COMPLETED = "COMPLETED", "Completed"
    CLOSED = "CLOSED", "Closed"


class Priority(models.IntegerChoices):
    LOW = 1, "Low"
    NORMAL = 2, "Normal"
    HIGH = 3, "High"
    URGENT = 4, "Urgent"


CATEGORIES = [
    (value, label)
    for value, label in (
        ("plumbing", "Plumbing"),
        ("electrical", "Electrical"),
        ("heating_cooling", "Heating/cooling"),
        ("appliance", "Appliance"),
        ("structural", "Structural"),
        ("exterior", "Exterior"),
        ("pest", "Pest"),
        ("security", "Lock/security"),
        ("general", "General"),
        ("other", "Other"),
    )
]


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=255, blank=True)
    trades = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class RequestQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user.is_authenticated or not user.is_active:
            return self.none()
        if user.is_manager_or_above:
            return self
        if user.is_tenant:
            return self.filter(audiences__lease__lease_tenants__tenant=user).distinct()
        return self.filter(assigned_to=user)


class MaintenanceRequest(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    property = models.ForeignKey("properties.Property", on_delete=models.PROTECT)
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, null=True, blank=True)
    reporting_lease = models.ForeignKey(
        "leases.Lease", on_delete=models.PROTECT, null=True, blank=True
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="maintenance_reported"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORIES)
    priority = models.PositiveSmallIntegerField(choices=Priority, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="maintenance_assigned",
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    schedule_window = models.CharField(max_length=100, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = RequestQuerySet.as_manager()

    class Meta:
        ordering = ("-priority", "created_at", "pk")
        indexes = [models.Index(fields=["status", "priority", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=Status.values), name="maintenance_valid_status"
            ),
            models.CheckConstraint(
                condition=Q(priority__in=[1, 2, 3, 4]), name="maintenance_valid_priority"
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="SCHEDULED") | Q(scheduled_for__isnull=False) | ~Q(schedule_window="")
                ),
                name="maintenance_schedule_date",
            ),
        ]

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        raise ValidationError("Maintenance history is retained; close the request instead.")


class Audience(models.Model):
    request = models.ForeignKey(
        MaintenanceRequest, on_delete=models.PROTECT, related_name="audiences"
    )
    lease = models.ForeignKey("leases.Lease", on_delete=models.PROTECT)
    permission_to_enter = models.BooleanField(default=False)
    permission_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    permission_at = models.DateTimeField(auto_now_add=True)
    unresolved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "lease"], name="maintenance_one_audience")
        ]

    def __str__(self):
        return str(self.lease)


class UpdateQuerySet(models.QuerySet):
    def visible_to(self, user):
        requests = MaintenanceRequest.objects.visible_to(user)
        rows = self.filter(request__in=requests)
        if user.is_tenant:
            rows = rows.filter(lease__lease_tenants__tenant=user).distinct()
        return rows


class Update(models.Model):
    request = models.ForeignKey(
        MaintenanceRequest, on_delete=models.PROTECT, related_name="updates"
    )
    # Null is INTERNAL. A lease is a private conversation, never a property-wide thread.
    lease = models.ForeignKey("leases.Lease", on_delete=models.PROTECT, null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    kind = models.CharField(max_length=20, default="NOTE")
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    objects = UpdateQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"Update #{self.pk} on request #{self.request_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if any(
                getattr(old, key) != getattr(self, key)
                for key in ("request_id", "lease_id", "author_id", "kind")
            ):
                raise ValidationError(
                    "An update's audience and identity cannot be changed. "
                    "Publish a separate update."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Updates are retained; add a correction instead.")


class AppendOnly(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("This history is immutable. Record a correction instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("This history cannot be deleted.")


class Revision(AppendOnly):
    update = models.ForeignKey(Update, on_delete=models.PROTECT, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    previous_body = models.TextField()
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Revision of update #{self.update_id}"


class Cost(AppendOnly):
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.PROTECT, related_name="costs")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    direction = models.CharField(
        max_length=8,
        choices=[("INCREASE", "Expense/increase"), ("DECREASE", "Reduction")],
        default="INCREASE",
    )
    corrects = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )
    description = models.CharField(max_length=255)
    incurred_on = models.DateField()
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True)
    reference = models.CharField(max_length=200, blank=True)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="maintenance_positive_cost"),
            models.CheckConstraint(
                condition=Q(direction="INCREASE") | Q(direction="DECREASE", corrects__isnull=False),
                name="maintenance_cost_direction",
            ),
        ]

    def __str__(self):
        return f"{self.incurred_on}: {self.description} (${self.effect})"

    @property
    def effect(self):
        return self.amount if self.direction == "INCREASE" else -self.amount

    @property
    def net_amount(self):
        return self.effect + sum((item.effect for item in self.corrections.all()), Decimal("0.00"))


def attachment_path(instance, filename):
    instance.original_name = Path(filename.replace("\\", "/")).name[:255]
    return f"maintenance/{uuid4().hex}{Path(filename).suffix.lower()}"


class Attachment(models.Model):
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    update = models.ForeignKey(
        Update, on_delete=models.PROTECT, null=True, blank=True, related_name="attachments"
    )
    cost = models.ForeignKey(
        Cost, on_delete=models.PROTECT, null=True, blank=True, related_name="attachments"
    )
    file = models.FileField(upload_to=attachment_path, max_length=255, blank=True)
    original_name = models.CharField(max_length=255)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    removal_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(update__isnull=False, cost__isnull=True)
                    | Q(update__isnull=True, cost__isnull=False)
                ),
                name="maintenance_attachment_parent",
            )
        ]

    def __str__(self):
        return self.original_name


class Recharge(AppendOnly):
    cost = models.ForeignKey(Cost, on_delete=models.PROTECT, related_name="recharges")
    batch = models.UUIDField()
    lease = models.ForeignKey("leases.Lease", on_delete=models.PROTECT)
    charge = models.OneToOneField(
        "ledger.Charge", on_delete=models.PROTECT, related_name="maintenance_recharge"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cost", "batch", "lease"], name="maintenance_recharge_once"
            )
        ]

    def __str__(self):
        return f"Repair charge #{self.charge_id}"


class Notification(models.Model):
    update = models.ForeignKey(Update, on_delete=models.PROTECT, related_name="notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    portal_url = models.URLField(max_length=500)
    status = models.CharField(max_length=12, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["update", "recipient"], name="maintenance_notification_once"
            )
        ]

    def __str__(self):
        return f"Maintenance email #{self.pk}: {self.status}"


class NotificationAttempt(AppendOnly):
    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name="deliveries"
    )
    outcome = models.CharField(max_length=12)
    error = models.CharField(max_length=255, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("attempted_at", "pk")

    def __str__(self):
        return f"Email attempt #{self.pk}: {self.outcome}"
