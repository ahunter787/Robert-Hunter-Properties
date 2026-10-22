"""Reviewed opening balances: balanced, immutable and manager-only."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import JournalEntry, OpeningBalanceBatch
from apps.audit.models import AuditEvent
from tests.factories import make_manager, make_property, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def formset_data(**lines):
    """Build a plain-formset POST for the default prefix ``form``."""
    rows = list(lines.values())
    data = {
        "form-TOTAL_FORMS": str(len(rows)),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "as_of": TODAY.isoformat(),
        "note": "Prepared from the closing statement; reviewed by the owner's accountant.",
    }
    for index, row in enumerate(rows):
        for key, value in row.items():
            data[f"form-{index}-{key}"] = str(value)
    return data


def test_balanced_opening_balances_post_one_immutable_journal():
    from apps.accounting.models import ChartAccount

    batch = services.post_opening_batch(
        as_of=TODAY,
        note="Closing statement, reviewed",
        lines=[
            {"account": "1110", "debit": Decimal("5000.00")},
            {"account": "3070", "credit": Decimal("5000.00")},
        ],
        actor=make_manager(username="opening-poster"),
    )

    assert batch.journal is not None
    assert batch.journal.source_key.startswith("opening:")
    batch.refresh_from_db()
    assert batch.lines.count() == 2
    assert AuditEvent.objects.filter(action="ACCOUNTING_OPENING_POSTED").exists()
    assert services.trial_balance()
    assert ChartAccount.objects.get(code="1110").kind == "ASSET"


def test_opening_balances_must_balance():
    with pytest.raises(Exception, match="do not balance"):
        services.post_opening_batch(
            as_of=TODAY,
            note="bad",
            lines=[
                {"account": "1110", "debit": Decimal("100.00")},
                {"account": "3070", "credit": Decimal("90.00")},
            ],
            actor=make_manager(username="opening-unbalanced"),
        )
    assert not OpeningBalanceBatch.objects.exists()


def test_income_accounts_are_not_opening_accounts():
    with pytest.raises(Exception, match="asset, liability and equity"):
        services.post_opening_batch(
            as_of=TODAY,
            note="bad",
            lines=[
                {"account": "4000", "debit": Decimal("100.00")},
                {"account": "3070", "credit": Decimal("100.00")},
            ],
            actor=make_manager(username="opening-income"),
        )


def test_a_manager_can_post_opening_balances_through_the_screen(client):
    from apps.accounting.models import ChartAccount

    prop = make_property()
    manager = make_manager(username="opening-manager")
    client.force_login(manager)
    bank = ChartAccount.objects.get(code="1110")
    equity = ChartAccount.objects.get(code="3070")

    response = client.post(
        reverse("accounting:opening-create"),
        formset_data(
            bank={
                "account": bank.pk,
                "debit": "2500.00",
                "credit": "0.00",
                "property": prop.pk,
            },
            equity={"account": equity.pk, "debit": "0.00", "credit": "2500.00"},
        ),
    )

    assert response.status_code == 302
    batch = OpeningBalanceBatch.objects.get()
    assert batch.journal is not None
    assert JournalEntry.objects.get(source_key=batch.journal.source_key).lines.count() == 2


def test_the_opening_screen_rejects_an_unbalanced_post(client):
    from apps.accounting.models import ChartAccount

    manager = make_manager(username="opening-unbalanced-ui")
    client.force_login(manager)
    bank = ChartAccount.objects.get(code="1110")
    equity = ChartAccount.objects.get(code="3070")

    response = client.post(
        reverse("accounting:opening-create"),
        formset_data(
            bank={"account": bank.pk, "debit": "2500.00", "credit": "0.00"},
            equity={"account": equity.pk, "debit": "0.00", "credit": "2400.00"},
        ),
    )

    assert response.status_code == 200
    assert not OpeningBalanceBatch.objects.exists()


def test_tenants_cannot_reach_opening_balances(client):
    client.force_login(make_tenant(username="opening-tenant"))
    assert client.get(reverse("accounting:opening-list")).status_code == 403
    assert client.get(reverse("accounting:opening-create")).status_code == 403
