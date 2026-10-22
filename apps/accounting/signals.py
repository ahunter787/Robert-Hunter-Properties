"""Kernel events that do not have a convenient service call site get posted here.

The only one in B1 is a credit application: applications are created from several reviewed
paths, and the GL consequence depends on the source (a receipt is already in AR; an opening
credit held in 2400 is not). The signal posts idempotently by the application row's own key.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ledger.models import FundsApplication


@receiver(post_save, sender=FundsApplication, dispatch_uid="accounting_post_application")
def post_application(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.accounting import services

    services.post_application(instance)
