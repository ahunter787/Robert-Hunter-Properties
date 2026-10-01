"""Portfolio model behaviour: constraints, protection, and the small helpers."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.properties.models import Property, Unit
from tests.factories import make_property, make_unit

pytestmark = pytest.mark.django_db


def test_property_name_is_unique_case_insensitively():
    make_property(name="Maple Street Duplex")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_property(name="maple street duplex")


def test_properties_may_share_an_address():
    # A duplex split into two records, or a renamed building, is a real case.
    make_property(name="Front House", street="12 Maple St")
    make_property(name="Rear House", street="12 Maple St")

    assert Property.objects.count() == 2


def test_address_line_renders_the_whole_address():
    assert make_property().address_line == "12 Maple St, Springfield, IL 62704"


def test_properties_are_in_service_by_default():
    assert make_property().is_active is True


def test_active_queryset_filters_out_retired_records():
    make_property(name="Retired", is_active=False)
    make_property(name="Working")

    assert list(Property.objects.active().values_list("name", flat=True)) == ["Working"]


def test_property_orders_by_name():
    make_property(name="Zebra Court")
    make_property(name="Apple Lane")

    assert list(Property.objects.values_list("name", flat=True)) == ["Apple Lane", "Zebra Court"]


def test_unit_identifier_is_unique_within_a_property():
    property_ = make_property()
    make_unit(property_, identifier="A")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_unit(property_, identifier="A")


def test_the_same_identifier_is_allowed_at_another_property():
    make_unit(make_property(name="One"), identifier="A")
    make_unit(make_property(name="Two"), identifier="A")

    assert Unit.objects.filter(identifier="A").count() == 2


def test_unit_label_names_the_property_and_the_unit():
    assert make_unit(make_property(name="Maple Street Duplex"), identifier="4").label == (
        "Maple Street Duplex · 4"
    )


def test_deleting_a_property_with_units_is_protected():
    property_ = make_property()
    make_unit(property_, identifier="A")

    with pytest.raises(ProtectedError):
        property_.delete()

    assert Property.objects.filter(pk=property_.pk).exists()


def test_deleting_a_property_without_units_is_allowed():
    property_ = make_property()

    property_.delete()

    assert not Property.objects.filter(pk=property_.pk).exists()


def test_deleting_units_then_the_property_works():
    property_ = make_property()
    make_unit(property_, identifier="A")

    property_.units.all().delete()
    property_.delete()

    assert Property.objects.count() == 0


def test_unit_active_queryset_filters_out_retired_units():
    property_ = make_property()
    make_unit(property_, identifier="Retired", is_active=False)
    make_unit(property_, identifier="Working")

    assert list(property_.units.active().values_list("identifier", flat=True)) == ["Working"]


def test_half_baths_are_accepted():
    unit = make_unit(bathrooms=Decimal("1.5"))

    unit.refresh_from_db()
    assert unit.bathrooms == Decimal("1.5")


def test_zip_code_is_validated():
    property_ = make_property(postal_code="not-a-zip")

    with pytest.raises(ValidationError):
        property_.full_clean()


def test_nine_digit_zip_codes_are_accepted():
    property_ = make_property(postal_code="62704-1234")

    property_.full_clean()


def test_state_must_be_a_known_code():
    property_ = make_property(state="XX")

    with pytest.raises(ValidationError):
        property_.full_clean()


def test_optional_unit_details_may_be_empty():
    unit = make_unit(bedrooms=None, bathrooms=None)

    assert unit.bedrooms is None
    assert unit.bathrooms is None
