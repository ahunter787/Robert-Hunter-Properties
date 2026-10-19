"""A household change freezes old shared threads, including changes through admin."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.leases.models import LeaseTenant


@receiver(pre_save, sender=LeaseTenant)
def remember_membership(sender, instance, **kwargs):
    instance._comm_old = (
        sender.objects.filter(pk=instance.pk).values("lease_id", "tenant_id").first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=LeaseTenant)
@receiver(post_delete, sender=LeaseTenant)
def membership_changed(sender, instance, **kwargs):
    from .services import freeze_household

    old = getattr(instance, "_comm_old", None)
    freeze_household(instance.lease_id)
    if old and old["lease_id"] != instance.lease_id:
        freeze_household(old["lease_id"])
