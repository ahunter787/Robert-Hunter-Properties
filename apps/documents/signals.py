"""Deleting a document row deletes its stored file.

Otherwise every removed document leaves its bytes behind: a file nobody can reach,
still taking space, and still there if the row is gone for a reason (ADR-022).
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.documents.models import Document

logger = logging.getLogger("apps.documents")


@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except OSError:  # pragma: no cover - storage refused to remove the file
        logger.warning("could not remove the stored file for document=%s", instance.pk)
