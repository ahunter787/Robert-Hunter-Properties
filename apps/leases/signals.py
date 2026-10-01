"""Model signals for leases.

Deleting a lease deletes its stored document, so uploads do not accumulate as
orphans — including deletions performed from the Django admin.
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.leases.models import Lease

logger = logging.getLogger("apps.leases")


@receiver(post_delete, sender=Lease)
def delete_lease_document(sender, instance, **kwargs):
    if not instance.lease_file:
        return
    try:
        instance.lease_file.delete(save=False)
    except OSError:  # pragma: no cover - storage refused to remove the file
        logger.warning("could not remove the lease document for lease=%s", instance.pk)
