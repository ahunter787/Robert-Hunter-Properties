"""Real populated-field edit sequences, explicit allocation and signed review."""

from decimal import Decimal

import pytest
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.ledger.models import Charge
from apps.responsibilities import services
from tests.factories import (
    make_charge,
    make_cycle,
    make_lease,
    make_manager,
    make_property,
    make_responsibility,
    make_share,
    make_tenant,
    make_unit,
)
from tests.responsibilities.helpers import allocation_page, new_bill_page, payload, reviewed_save

pytestmark = pytest.mark.django_db


@pytest.fixture
def bill(client):
    client.force_login(make_manager())
    prop = make_property()
    units = [
        make_unit(for_property=prop, identifier=name, square_feet=size)
        for name, size in [("Michael", 1450), ("Peter", 2000)]
    ]
    responsibility = make_responsibility(prop, label="Gas")
    cycle = make_cycle(
        responsibility,
        total_amount=Decimal("237.00"),
        months=3,
        starts_on=timezone.localdate().replace(day=1),
    )
    for unit, amount in zip(units, ("33.20", "45.80"), strict=True):
        make_share(cycle, unit, monthly_amount=Decimal(amount))
    return cycle, units


def url(cycle):
    return reverse("responsibilities:cycle-shares", args=[cycle.pk])


def stored(cycle):
    return dict(cycle.shares.values_list("unit_id", "monthly_amount"))


def test_existing_bill_begins_with_read_only_summary(client, bill):
    cycle, _ = bill
    response = client.get(url(cycle))
    assert response.context["step"] == "details"
    assert b"$237.00" in response.content and b"$79.00" in response.content
    assert b'name="unit_' not in response.content


def test_preserves_saved_amounts_and_defaults_remainder_to_rhp(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    assert page.context["allocation"]["remainder"].value() == "rhp"
    assert payload(page)[f"unit_{units[0].pk}"] == "33.20"
    assert payload(page)[f"percent_{units[0].pk}"] == "42.03"


def test_dollar_edit_ignores_stale_display_percent_and_changes_only_recipient(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(
        url(cycle), payload(page, **{f"unit_{units[0].pk}": "40.00", "remainder": str(units[1].pk)})
    )
    assert result.context["allocation"].amounts() == {
        units[0].pk: Decimal("40"),
        units[1].pk: Decimal("39"),
    }
    assert payload(result)[f"percent_{units[0].pk}"] == "50.63"
    assert stored(cycle)[units[0].pk] == Decimal("33.20")


def test_percentage_edit_updates_both_fields(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(
        url(cycle),
        payload(
            page,
            **{
                f"basis_{units[0].pk}": "percent",
                f"percent_{units[0].pk}": "50.00",
                "remainder": str(units[1].pk),
            },
        ),
    )
    assert payload(result)[f"unit_{units[0].pk}"] == "39.50"
    assert payload(result)[f"unit_{units[1].pk}"] == "39.50"
    assert payload(result)[f"percent_{units[0].pk}"] == "50.00"


def test_repeated_switching_preserves_exact_dollars(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    for basis, value, expected in [
        ("amount", "40.00", "40.00"),
        ("percent", "25", "19.75"),
        ("amount", "33.20", "33.20"),
    ]:
        key = "unit" if basis == "amount" else "percent"
        page = client.post(
            url(cycle),
            payload(
                page,
                **{
                    f"basis_{units[0].pk}": basis,
                    f"{key}_{units[0].pk}": value,
                    "remainder": str(units[1].pk),
                },
            ),
        )
        assert payload(page)[f"unit_{units[0].pk}"] == expected


def test_no_remainder_unit_never_replaces_other_manual_amount(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, **{f"unit_{units[0].pk}": "20"}))
    assert result.context["allocation"].amounts()[units[1].pk] == Decimal("45.80")
    assert result.context["worksheet"].left == Decimal("13.20")


def test_third_manual_unit_unchanged_when_first_is_remainder(client, bill):
    cycle, units = bill
    third = make_unit(
        for_property=cycle.responsibility.property, identifier="Third", square_feet=400
    )
    make_share(cycle, third, monthly_amount=Decimal("0"))
    page = allocation_page(client, cycle)
    result = client.post(
        url(cycle),
        payload(
            page,
            **{
                "remainder": str(units[0].pk),
                f"unit_{units[1].pk}": "30",
                f"unit_{third.pk}": "10",
            },
        ),
    )
    assert result.context["allocation"].amounts() == {
        units[0].pk: Decimal("39"),
        units[1].pk: Decimal("30"),
        third.pk: Decimal("10"),
    }


def test_overallocation_updates_pair_but_blocks_review(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(
        url(cycle), payload(page, action="review", **{f"unit_{units[0].pk}": "40"})
    )
    assert result.context["step"] == "allocate"
    assert result.context["worksheet"].over == Decimal("6.80")
    assert payload(result)[f"percent_{units[0].pk}"] == "50.63"
    assert stored(cycle)[units[0].pk] == Decimal("33.20")


@pytest.mark.parametrize("method", ["size", "equal"])
def test_explicit_allocation_methods_conserve_cents(client, bill, method):
    cycle, _ = bill
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, allocation_method=method))
    assert result.context["worksheet"].assigned == Decimal("79.00")
    assert sum(result.context["allocation"].amounts().values()) == Decimal("79.00")
    assert AuditEvent.objects.count() == 0


def test_size_requires_all_sizes_instead_of_silent_equal_fallback(client, bill):
    cycle, units = bill
    units[0].square_feet = None
    units[0].save()
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, allocation_method="size"))
    assert b"Record square footage for every unit" in result.content
    assert stored(cycle)[units[0].pk] == Decimal("33.20")


@pytest.mark.parametrize(
    "field,value", [("unit", ""), ("unit", "-1"), ("unit", "no"), ("percent", "101")]
)
def test_invalid_selected_input_refused(client, bill, field, value):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(
        url(cycle),
        payload(
            page,
            action="review",
            **{
                f"{field}_{units[0].pk}": value,
                f"basis_{units[0].pk}": "amount" if field == "unit" else "percent",
            },
        ),
    )
    assert result.context["allocation"].errors
    assert result.context["step"] == "allocate"


def test_explicit_exclusion_removes_unit_only_after_review(client, bill):
    cycle, units = bill
    response = reviewed_save(client, cycle, **{f"basis_{units[0].pk}": "excluded"})
    assert response.status_code == 302
    assert stored(cycle) == {units[1].pk: Decimal("45.80")}
    assert not Charge.objects.exists()


def test_review_and_back_write_nothing_and_save_matches_review(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    review = client.post(
        url(cycle),
        payload(
            page, action="review", **{f"unit_{units[0].pk}": "40", "remainder": str(units[1].pk)}
        ),
    )
    assert review.context["step"] == "review"
    assert stored(cycle)[units[0].pk] == Decimal("33.20")
    assert AuditEvent.objects.count() == 0
    back = client.post(url(cycle), payload(review, action="back"))
    assert back.context["step"] == "allocate"
    assert AuditEvent.objects.count() == 0
    result = client.post(url(cycle), payload(review, action="save"))
    assert result.status_code == 302
    assert stored(cycle) == {units[0].pk: Decimal("40"), units[1].pk: Decimal("39")}
    assert AuditEvent.objects.count() == 1
    assert not Charge.objects.exists()


@pytest.mark.parametrize("mutation", ["amounts", "bill", "unit", "new_unit", "charge"])
def test_concurrent_changes_invalidate_review(client, bill, mutation):
    cycle, units = bill
    page = allocation_page(client, cycle)
    review = client.post(url(cycle), payload(page, action="review"))
    if mutation == "amounts":
        services.set_shares(cycle, {units[0].pk: Decimal("20")})
    elif mutation == "bill":
        cycle.total_amount = Decimal("240")
        cycle.save()
    elif mutation == "unit":
        units[0].square_feet = 1500
        units[0].save()
    elif mutation == "new_unit":
        make_unit(for_property=cycle.responsibility.property, identifier="new")
    else:
        lease = make_lease(units[0], start_date=cycle.starts_on)
        make_charge(
            lease,
            kind="RESPONSIBILITY",
            responsibility=cycle.responsibility,
            due_date=cycle.starts_on,
        )
    before = stored(cycle)
    result = client.post(url(cycle), payload(review, action="save"))
    assert result.status_code == 200
    assert stored(cycle) == before
    assert b"changed" in result.content or b"posted charges" in result.content


def test_tampered_review_and_direct_save_refused(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    review = client.post(url(cycle), payload(page, action="review"))
    for data in (
        payload(page, action="save"),
        payload(review, action="save", **{f"unit_{units[0].pk}": "10"}),
        payload(review, action="save", review_token="forged"),
    ):
        result = client.post(url(cycle), data)
        assert result.status_code == 200
        assert stored(cycle)[units[0].pk] == Decimal("33.20")


def test_expired_review_refused(client, bill):
    cycle, _ = bill
    page = allocation_page(client, cycle)
    review = client.post(url(cycle), payload(page, action="review"))
    # A validly signed, intentionally ancient timestamp exercises expiry, not forgery.
    value = signing.loads(review.context["review_token"], salt="expense-review")

    class AncientSigner(signing.TimestampSigner):
        def timestamp(self):
            return "1"

    token = AncientSigner(salt="expense-review").sign_object(value)
    result = client.post(url(cycle), payload(review, action="save", review_token=token))
    assert b"expired or is invalid" in result.content


def test_preview_compatibility_endpoint_cannot_save(client, bill):
    cycle, _ = bill
    page = allocation_page(client, cycle)
    review = client.post(url(cycle), payload(page, action="review"))
    endpoint = reverse("responsibilities:cycle-shares-calculate", args=[cycle.pk])
    result = client.post(endpoint, payload(review, action="save"))
    assert result.status_code == 200
    assert AuditEvent.objects.count() == 0


def test_foreign_remainder_unit_refused(client, bill):
    cycle, _ = bill
    foreign = make_unit(for_property=make_property(name="Another property"))
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, action="review", remainder=str(foreign.pk)))
    assert result.context["allocation"].errors


def test_tenant_cannot_read_preview_or_save(client, bill):
    cycle, _ = bill
    client.force_login(make_tenant())
    assert client.get(url(cycle)).status_code == 403
    assert client.post(url(cycle), {"action": "save"}).status_code == 403
    assert (
        client.post(
            reverse("responsibilities:cycle-shares-calculate", args=[cycle.pk]), {}
        ).status_code
        == 403
    )


def test_new_bill_all_steps_preview_only_until_save(client, bill):
    existing, units = bill
    responsibility = existing.responsibility
    endpoint = reverse("responsibilities:cycle-stage", args=[responsibility.pk])
    page = new_bill_page(
        client,
        responsibility,
        starts_on="2027-01-01",
        months=3,
        total_amount="700.00",
        note="invoice",
    )
    assert page.context["step"] == "allocate"
    allocated = client.post(endpoint, payload(page, allocation_method="size"))
    assert responsibility.cycles.count() == 1
    review = client.post(endpoint, payload(allocated, action="review"))
    assert review.context["step"] == "review"
    assert review.context["rounding"] == Decimal("-0.01")
    assert b"Monthly rounding difference" in review.content
    assert responsibility.cycles.count() == 1
    saved = client.post(endpoint, payload(review, action="save"))
    assert saved.status_code == 302
    cycle = responsibility.cycles.get(starts_on="2027-01-01")
    assert sum(stored(cycle).values()) == Decimal("233.33")
    assert {s.unit_id for s in cycle.shares.all()} == {u.pk for u in units}
    assert cycle.note == "invoice"
    assert not Charge.objects.exists()


def test_vacancy_and_rhp_share_are_explicit(client, bill):
    cycle, units = bill
    make_lease(units[0], start_date=cycle.starts_on)
    page = allocation_page(client, cycle)
    review = client.post(url(cycle), payload(page, action="review"))
    assert review.context["rhpshare"] == Decimal("45.80")
    assert b"RHP carries this allocation" in review.content


def test_no_units_allocates_bill_to_rhp(client, bill):
    existing, _ = bill
    responsibility = make_responsibility(make_property(name="Empty property"))
    page = new_bill_page(
        client, responsibility, starts_on="2027-01-01", months=1, total_amount="100"
    )
    endpoint = reverse("responsibilities:cycle-stage", args=[responsibility.pk])
    preview = client.post(endpoint, payload(page, allocation_method="equal"))
    review = client.post(endpoint, payload(preview, action="review"))
    assert review.context["rhpshare"] == Decimal("100")


def test_browser_enhancement_tracks_basis_and_discards_stale_responses(client, bill):
    cycle, _ = bill
    page = allocation_page(client, cycle)
    assert b"expense-allocation.js" in page.content
    assert b"Update calculation" in page.content
    assert b'hx-swap="none"' not in page.content


def test_back_to_bill_details_preserves_unsaved_allocation(client, bill):
    existing, units = bill
    responsibility = existing.responsibility
    endpoint = reverse("responsibilities:cycle-stage", args=[responsibility.pk])
    page = new_bill_page(
        client,
        responsibility,
        starts_on="2027-01-01",
        months=3,
        total_amount="300",
        note="invoice reference",
    )
    data = payload(
        page,
        action="details",
        **{
            f"unit_{units[0].pk}": "25",
            "remainder": str(units[1].pk),
            "note": "Custom usage split",
        },
    )
    details = client.post(endpoint, data)
    assert details.context["step"] == "details"
    # These are the hidden draft values rendered alongside bill-detail fields.
    data = payload(details, action="allocate")
    data.update(dict(details.context["draft"]))
    allocation = client.post(endpoint, data)
    assert allocation.context["allocation"].amounts()[units[0].pk] == Decimal("25")
    review = client.post(endpoint, payload(allocation, action="review"))
    saved = client.post(endpoint, payload(review, action="save"))
    assert saved.status_code == 302
    cycle = responsibility.cycles.get(starts_on="2027-01-01")
    assert cycle.note == "invoice reference"
    assert cycle.shares.get(unit=units[0]).note == "Custom usage split"


def test_large_bill_dollars_never_roundtrip_through_percentage(client, bill):
    cycle, units = bill
    cycle.total_amount = Decimal("90000")
    cycle.save()
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, **{f"unit_{units[0].pk}": "1234.56"}))
    exact = result.context["allocation"].amounts()[units[0].pk]
    assert exact == Decimal("1234.56")
    assert (
        services.share_amount(
            services.share_percent(exact, cycle.monthly_total), cycle.monthly_total
        )
        != exact
    )
    review = client.post(url(cycle), payload(result, action="review"))
    assert client.post(url(cycle), payload(review, action="save")).status_code == 302
    assert stored(cycle)[units[0].pk] == exact


def test_remainder_fields_are_read_only_and_explicitly_labelled(client, bill):
    cycle, units = bill
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, remainder=str(units[1].pk)))
    assert result.context["allocation"][f"unit_{units[1].pk}"].field.widget.attrs["readonly"]
    assert b"Calculated remainder recipient" in result.content


def test_three_way_equal_allocation_absorbs_rounding(client, bill):
    cycle, _ = bill
    third = make_unit(
        for_property=cycle.responsibility.property, identifier="Third", square_feet=100
    )
    page = allocation_page(client, cycle)
    result = client.post(url(cycle), payload(page, allocation_method="equal"))
    assert sum(result.context["allocation"].amounts().values()) == Decimal("79.00")
    assert third.pk in result.context["allocation"].amounts()
