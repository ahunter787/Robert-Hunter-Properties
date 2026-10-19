"""Model signals for the portfolio.

Deleting a property deletes its banner file, so uploads do not accumulate as
orphans - including deletions performed from the Django admin rather than the
RHP screens.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.properties.models import Property, Unit

logger = logging.getLogger("apps.properties")


def remove_banner_file(name, storage):
    if not name or Property.objects.filter(banner_image=name).exists():
        return
    try:
        storage.delete(name)
    except OSError:
        logger.warning("could not remove an unreferenced property banner")


@receiver(post_delete, sender=Property)
def delete_banner_file(sender, instance, **kwargs):
    if not instance.banner_image:
        return
    try:
        instance.banner_image.delete(save=False)
    except OSError:  # pragma: no cover - storage refused to remove the file
        logger.warning("could not remove the banner file for property=%s", instance.pk)


def remove_unit_photo(name, storage):
    if not name or Unit.objects.filter(photo=name).exists():
        return
    try:
        storage.delete(name)
    except OSError:
        logger.warning("could not remove an unreferenced unit photo")


@receiver(post_delete, sender=Unit)
def delete_unit_photo(sender, instance, **kwargs):
    if instance.photo:
        name, storage = instance.photo.name, instance.photo.storage
        transaction.on_commit(lambda: remove_unit_photo(name, storage))
