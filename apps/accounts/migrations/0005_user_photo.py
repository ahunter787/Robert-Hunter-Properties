from django.db import migrations, models

import apps.accounts.models


def copy_legacy_tenant_photos(apps, schema_editor):
    """Promote existing tenant photos to the account-level field.

    The file on disk is unchanged; only the field that points at it moves. The
    old TenantProfile.photo column stays for historical rows and is no longer
    read by the application.
    """
    TenantProfile = apps.get_model("accounts", "TenantProfile")
    User = apps.get_model("accounts", "User")
    for profile in TenantProfile.objects.exclude(photo="").iterator():
        if profile.photo:
            User.objects.filter(pk=profile.user_id).update(photo=profile.photo.name)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_tenantprofile_photo")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="photo",
            field=models.ImageField(
                blank=True,
                help_text="JPEG, PNG, or WebP. Shown beside the account name.",
                null=True,
                upload_to=apps.accounts.models.account_photo_path,
            ),
        ),
        migrations.RunPython(copy_legacy_tenant_photos, migrations.RunPython.noop),
    ]
