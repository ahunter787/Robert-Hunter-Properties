"""The additive photo field preserves existing property/unit identity and facts."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_unit_photo_upgrade_preserves_existing_units(restore_schema):
    before = [("properties", "0004_property_cam_rate_per_sqft")]
    after = [("properties", "0005_unit_photo")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    apps = executor.loader.project_state(before).apps
    prop = apps.get_model("properties", "Property").objects.create(
        name="Preserved building",
        street="100 Example Ave",
        city="Example",
        state="OR",
        postal_code="97000",
    )
    unit = apps.get_model("properties", "Unit").objects.create(
        property=prop,
        identifier="Preserved unit",
        square_feet=950,
    )
    executor = MigrationExecutor(connection)
    executor.migrate(after)
    apps = executor.loader.project_state(after).apps
    result = apps.get_model("properties", "Unit").objects.get(pk=unit.pk)
    assert result.property_id == prop.pk
    assert result.identifier == "Preserved unit" and result.square_feet == 950
    assert not result.photo
