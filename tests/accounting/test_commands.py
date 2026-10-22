"""The bridge from existing sub-ledger history to the GL."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.accounting import services
from apps.accounting.models import JournalEntry
from apps.ledger.models import PaymentStatus
from tests.factories import make_charge, make_lease, make_payment

pytestmark = pytest.mark.django_db


def test_sync_posts_existing_charges_and_payments_and_ties():
    lease = make_lease()
    charge = make_charge(lease, amount=Decimal("400.00"))
    payment = make_payment(lease, amount=Decimal("400.00"), status=PaymentStatus.CLEARED)
    assert not JournalEntry.objects.filter(
        source_key__in=[f"charge:{charge.pk}:created", f"payment:{payment.pk}:recorded"]
    ).exists()

    call_command("accounting_sync", verbosity=0)

    assert JournalEntry.objects.filter(source_key=f"charge:{charge.pk}:created").exists()
    assert JournalEntry.objects.filter(source_key=f"payment:{payment.pk}:recorded").exists()
    assert services.ar_control_tie()["difference"] == Decimal("0.00")


def test_sync_is_idempotent():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"))
    call_command("accounting_sync", verbosity=0)
    before = JournalEntry.objects.count()

    call_command("accounting_sync", verbosity=0)

    assert JournalEntry.objects.count() == before


def test_status_reports_the_tie():
    lease = make_lease()
    make_charge(lease, amount=Decimal("100.00"))
    call_command("accounting_sync", verbosity=0)
    call_command("accounting_status", verbosity=0)
