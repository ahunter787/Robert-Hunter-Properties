"""B2 vendor bills and AP: expense first, payment later, control must tie."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import VendorBill
from tests.factories import make_manager, make_property, make_tenant

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
ZERO = Decimal("0.00")
_counter = 0


def manager():
    global _counter
    _counter += 1
    return make_manager(username=f"bill-manager-{_counter}")


def bill(**overrides):
    values = {
        "property": make_property(),
        "vendor": None,
        "expense_account": "5000",
        "description": "Plumbing repair",
        "amount": Decimal("400.00"),
        "received_on": TODAY,
        "due_date": TODAY,
        "actor": manager(),
    }
    values.update(overrides)
    return services.record_vendor_bill(**values)


def test_a_vendor_bill_posts_expense_and_ap_and_ties():
    recorded = bill()

    journal = recorded.journal
    assert [
        (line.account.code, line.debit, line.credit)
        for line in journal.lines.select_related("account").order_by("pk")
    ] == [
        ("5000", Decimal("400.00"), ZERO),
        ("2100", ZERO, Decimal("400.00")),
    ]
    assert recorded.balance == Decimal("400.00")
    assert services.ap_control_tie()["difference"] == ZERO


def test_a_payment_reduces_ap_through_undeposited_funds():
    recorded = bill()
    payment = services.pay_vendor_bill(
        recorded,
        amount=Decimal("400.00"),
        paid_on=TODAY,
        method="CHECK",
        reference="1042",
        actor=manager(),
    )

    assert [
        (line.account.code, line.debit, line.credit)
        for line in payment.journal.lines.select_related("account").order_by("pk")
    ] == [
        ("2100", Decimal("400.00"), ZERO),
        ("1450", ZERO, Decimal("400.00")),
    ]
    assert recorded.balance == ZERO
    assert services.ap_control_tie()["difference"] == ZERO


def test_a_bill_cannot_be_overpaid():
    recorded = bill(amount=Decimal("100.00"))
    with pytest.raises(Exception, match="remaining balance"):
        services.pay_vendor_bill(recorded, amount=Decimal("150.00"), paid_on=TODAY, actor=manager())
    assert services.ap_control_tie()["difference"] == ZERO


def test_a_bill_must_use_an_expense_account():
    with pytest.raises(Exception, match="expense account"):
        bill(expense_account="1200")


def test_the_posting_is_idempotent_and_immutable():
    recorded = bill(amount=Decimal("50.00"))
    first = services.post_journal(
        source_key=f"bill:{recorded.pk}:recorded",
        event_type="vendor_bill.recorded",
        posted_on=TODAY,
        lines=[
            {"account": "5000", "debit": Decimal("50.00")},
            {"account": "2100", "credit": Decimal("50.00")},
        ],
        property=recorded.property,
    )
    assert first.pk == recorded.journal.pk
    recorded.amount = Decimal("60.00")
    with pytest.raises(Exception, match="immutable"):
        recorded.save()


def test_a_manager_records_and_pays_a_bill_through_the_screens(client):
    prop = make_property()
    manager_user = manager()
    client.force_login(manager_user)
    from apps.accounting.models import ChartAccount

    expense = ChartAccount.objects.get(code="5000")
    response = client.post(
        reverse("accounting:bill-create"),
        {
            "property": prop.pk,
            "vendor": "",
            "expense_account": expense.pk,
            "description": "Water heater",
            "amount": "650.00",
            "received_on": TODAY.isoformat(),
            "due_date": TODAY.isoformat(),
            "note": "Invoice attached at the office",
        },
    )
    assert response.status_code == 302
    recorded = VendorBill.objects.get()
    assert recorded.amount == Decimal("650.00")

    response = client.post(
        reverse("accounting:bill-detail", args=[recorded.pk]),
        {
            "amount": "650.00",
            "paid_on": TODAY.isoformat(),
            "method": "CHECK",
            "reference": "1050",
            "note": "",
        },
    )
    assert response.status_code == 302
    recorded.refresh_from_db()
    assert recorded.balance == ZERO
    assert services.ap_control_tie()["difference"] == ZERO


def test_tenants_cannot_reach_vendor_bills(client):
    client.force_login(make_tenant(username="bill-outsider"))
    assert client.get(reverse("accounting:bill-list")).status_code == 403
    assert client.get(reverse("accounting:bill-create")).status_code == 403
