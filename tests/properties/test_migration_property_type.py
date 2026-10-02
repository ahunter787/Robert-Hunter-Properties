"""The data migration that moved the designation from units to properties.

This is the only honest way to test a data migration: put the schema back where it
was, write rows in the old shape with raw model access, migrate forward, and check
what the data became. It runs against the test database, never the development one.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = ("properties", "0002_unit_type_map_pin_and_banner")
AFTER = ("properties", "0003_property_type_square_feet_and_amenities")


def migrate(target):
    """Move the schema to ``target`` and return the historical app registry."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


def make_at_0002(Property, name):
    return Property.objects.create(
        name=name,
        street="1 Migration Way",
        city="Portland",
        state="OR",
        postal_code="97201",
    )


def test_each_property_takes_the_designation_of_its_units():
    old = migrate(BEFORE)
    Property = old.get_model("properties", "Property")
    Unit = old.get_model("properties", "Unit")

    residential = make_at_0002(Property, "All Residential")
    Unit.objects.create(property=residential, identifier="1", unit_type="RESIDENTIAL")
    Unit.objects.create(property=residential, identifier="2", unit_type="RESIDENTIAL")

    commercial = make_at_0002(Property, "All Commercial")
    Unit.objects.create(property=commercial, identifier="Shop", unit_type="COMMERCIAL")

    mixed = make_at_0002(Property, "Mixed Use")
    Unit.objects.create(property=mixed, identifier="Shop", unit_type="COMMERCIAL")
    Unit.objects.create(property=mixed, identifier="Flat", unit_type="RESIDENTIAL")

    empty = make_at_0002(Property, "No Units")

    new = migrate(AFTER)
    NewProperty = new.get_model("properties", "Property")
    NewUnit = new.get_model("properties", "Unit")

    assert NewProperty.objects.get(pk=residential.pk).property_type == "RESIDENTIAL"
    assert NewProperty.objects.get(pk=commercial.pk).property_type == "COMMERCIAL"
    assert NewProperty.objects.get(pk=mixed.pk).property_type == "RESIDENTIAL", (
        "a mixed building resolves to residential rather than being guessed at"
    )
    assert NewProperty.objects.get(pk=empty.pk).property_type == "RESIDENTIAL"

    field_names = {field.name for field in NewUnit._meta.fields}
    assert "unit_type" not in field_names, "the old column is gone"

    Amenity = new.get_model("properties", "Amenity")
    assert Amenity.objects.count() >= 15, "the default amenities are seeded"
    assert Amenity.objects.filter(name="Parking", is_active=True).exists()


def test_the_units_are_not_lost_by_the_move():
    old = migrate(BEFORE)
    Property = old.get_model("properties", "Property")
    Unit = old.get_model("properties", "Unit")
    property_ = make_at_0002(Property, "Kept")
    Unit.objects.create(property=property_, identifier="A", unit_type="RESIDENTIAL")
    Unit.objects.create(property=property_, identifier="B", unit_type="COMMERCIAL")

    new = migrate(AFTER)
    NewUnit = new.get_model("properties", "Unit")

    assert sorted(NewUnit.objects.values_list("identifier", flat=True)) == ["A", "B"]


def test_the_reverse_step_pushes_the_designation_back_down():
    new = migrate(AFTER)
    Property = new.get_model("properties", "Property")
    Unit = new.get_model("properties", "Unit")
    commercial = Property.objects.create(
        name="Reverse Me",
        property_type="COMMERCIAL",
        street="1 Migration Way",
        city="Portland",
        state="OR",
        postal_code="97201",
    )
    unit = Unit.objects.create(property=commercial, identifier="Shop")

    try:
        old = migrate(BEFORE)
        OldUnit = old.get_model("properties", "Unit")
        assert OldUnit.objects.get(pk=unit.pk).unit_type == "COMMERCIAL"
    finally:
        # Leave the schema where the rest of the suite expects it.
        migrate(AFTER)
