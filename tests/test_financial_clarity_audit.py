"""Audit evidence, not an endorsement of cash classification or a product change."""

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

from apps.dashboard import services as dashboard
from apps.ledger.models import PaymentStatus
from tests.factories import make_admin, make_lease, make_manager, place_lease
from tools.publish_design import canonical

ROOT = Path(__file__).resolve().parents[1]


def test_outline_reflow_of_quoted_owner_text_preserves_word_changes():
    assert canonical("> Original words\n> wrapped here.") == canonical(
        "> Original words wrapped here."
    )
    assert canonical("> Original words.") != canonical("> Changed owner words.")


@pytest.mark.django_db
def test_audit_characterizes_starting_credit_as_held_credit_not_a_payment(settings):
    """F05 is resolved by ADR-028: an opening credit is a held credit, never a clearance."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    today = timezone.localdate()
    manager = make_manager()
    lease = make_lease(
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=300),
        billing_start_date=None,
    )
    place_lease(
        lease, make_admin(username="starting-credit-placer"), kind="CREDIT", amount="200.00"
    )
    lease.refresh_from_db()
    assert not lease.payments.exists(), "an opening credit is not a payment"
    assert not lease.payments.filter(status=PaymentStatus.CLEARED).exists()
    metrics = dashboard.project(manager)["metrics"]
    assert metrics["credits"].value == Decimal("200.00")
    assert metrics["month-payments"].value == Decimal("0.00")


def test_audit_examples_are_synthetic_proposals_with_print_exports():
    base = ROOT / "docs/design/financial-clarity"
    book = json.loads((base / "sources/financial-examples.json").read_text())
    assert len(book["pages"]) == 5
    for index, page in enumerate(book["pages"], 1):
        assert "Synthetic" in page["subtitle"]
        assert "Proposed" in page["subtitle"]
        assert (page["width"], page["height"]) == (792, 612)
        for element in page["elements"]:
            assert 30 <= element["x"] <= 762
            assert 80 <= element["y"] <= 582
            if element["type"] == "text":
                assert element["size"] >= 9
        for suffix in ("", "-grayscale"):
            stem = f"financial-examples{suffix}"
            assert (base / f"artifacts/{stem}-{index:02}.svg").exists()
            assert (base / f"artifacts/{stem}-{index}.png").exists()
    for suffix in ("", "-grayscale"):
        assert (
            (base / f"artifacts/financial-examples{suffix}.pdf").read_bytes().startswith(b"%PDF-")
        )
