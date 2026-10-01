"""Model signals for the portfolio.

Deleting a property deletes its banner file, so uploads do not accumulate as
orphans - including deletions performed from the Django admin rather than the
RHP screens.
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.properties.models import Property

logger = logging.getLogger("apps.properties")


@receiver(post_delete, sender=Property)
def delete_banner_file(sender, instance, **kwargs):
    if not instance.banner_image:
        return
    try:
        instance.banner_image.delete(save=False)
    except OSError:  # pragma: no cover - storage refused to remove the file
        logger.warning("could not remove the banner file for property=%s", instance.pk)
