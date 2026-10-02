"""The Commercial/Residential designation moves from the unit to the property.

Also adds square feet and amenities to units (ADR-006, revision).

The data step: each property takes the designation of its units, and is
commercial only when **every** one of them was commercial. A property with no
units, or a mixed one, becomes residential — a mixed building cannot be expressed
once the designation lives on the property, so it is resolved deterministically
here rather than guessed at silently. The reverse step copies the property's
designation back down to its units.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models

#: Frozen copy of the seed list: a migration must not change when app code does.
DEFAULT_AMENITIES = (
    "Parking",
    "Off-street parking",
    "Laundry in unit",
    "Laundry in building",
    "Dishwasher",
    "Air conditioning",
    "Balcony or patio",
    "Storage",
    "Fireplace",
    "Furnished",
    "Pet friendly",
    "Elevator",
    "Gym",
    "Pool",
    "Security system",
    "Utilities included",
    "Wheelchair accessible",
)


def designation_per_property(apps, schema_editor):
    """Give each property the designation its units had."""
    Property = apps.get_model("properties", "Property")
    for property_ in Property.objects.all():
        unit_types = set(property_.units.values_list("unit_type", flat=True))
        property_.property_type = (
            "COMMERCIAL" if unit_types == {"COMMERCIAL"} else "RESIDENTIAL"
        )
        property_.save(update_fields=["property_type"])


def designation_back_to_units(apps, schema_editor):
    """Best effort in reverse: every unit takes its property's designation."""
    Property = apps.get_model("properties", "Property")
    for property_ in Property.objects.all():
        property_.units.update(unit_type=property_.property_type)


def seed_amenities(apps, schema_editor):
    Amenity = apps.get_model("properties", "Amenity")
    for name in DEFAULT_AMENITIES:
        Amenity.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0002_unit_type_map_pin_and_banner"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="property_type",
            field=models.CharField(
                choices=[("RESIDENTIAL", "Residential"), ("COMMERCIAL", "Commercial")],
                db_index=True,
                default="RESIDENTIAL",
                help_text=(
                    "Bedrooms and bathrooms are only recorded for units in a residential "
                    "property."
                ),
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="unit",
            name="square_feet",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional. Leave blank when the size is not known.",
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(1000000)],
                verbose_name="square feet",
            ),
        ),
        migrations.CreateModel(
            name="Amenity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=60, unique=True)),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text=(
                            "Retired amenities stay on the units that have them but leave "
                            "the picker."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name_plural": "amenities",
                "ordering": ("name",),
            },
        ),
        migrations.AddField(
            model_name="unit",
            name="amenities",
            field=models.ManyToManyField(
                blank=True,
                help_text="Hold Ctrl (or Cmd) to choose more than one.",
                related_name="units",
                to="properties.amenity",
            ),
        ),
        # The designation is copied up before the column it came from is dropped.
        migrations.RunPython(designation_per_property, designation_back_to_units),
        # No reverse needed: rolling back drops the table this seeds.
        migrations.RunPython(seed_amenities, migrations.RunPython.noop),
        migrations.RemoveField(model_name="unit", name="unit_type"),
    ]
