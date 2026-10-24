"""Account photos: upload, serving, permissions, and the placeholder.

A photo is personal data, so the rules that apply to a lease document apply here
too: a randomised name on disk, served only through a permission-checked view,
and never reachable by guessing a URL. Any signed-in account can set its own
photo; administrators may set another account's photo. Managers and tenants
cannot change someone else's.
"""

import io
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from tests.factories import make_admin, make_manager, make_tenant

pytestmark = pytest.mark.django_db


def photo_upload(name: str = "portrait.png", fmt: str = "PNG", size=(300, 300)):
    """A real image, so Pillow's validation has something to read."""
    buffer = io.BytesIO()
    Image.new("RGB", size, "navy").save(buffer, format=fmt)
    content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def png_bytes(size=(300, 300), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "navy").save(buffer, format=fmt)
    return buffer.getvalue()


def noisy_png_bytes(size=(1500, 1500)) -> bytes:
    """Random pixels compress badly, which makes an honest multi-megabyte file."""
    width, height = size
    image = Image.frombytes("RGB", size, os.urandom(width * height * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def give_photo(account, name: str = "portrait.png", size=(300, 300)) -> str:
    """Store a real photo for an account, the way the upload view would."""
    account.photo.save(name, SimpleUploadedFile(name, png_bytes(size), content_type="image/png"))
    return account.photo.name


def test_account_without_portrait_does_not_inherit_previous_rows_photo(as_manager):
    first = make_tenant(username="first-portrait", first_name="A", last_name="Example")
    second = make_tenant(username="second-no-portrait", first_name="B", last_name="Example")
    give_photo(first)
    body = as_manager.get(reverse("manage:account-list")).content.decode()
    assert body.count(reverse("manage:account-photo", args=[first.pk])) == 1
    assert reverse("manage:account-photo", args=[second.pk]) not in body
    assert "No photo" in body


def test_photo_input_does_not_link_private_storage_names(as_admin):
    tenant = make_tenant(username="photo-widget")
    name = give_photo(tenant)
    body = as_admin.get(
        reverse("manage:account-detail", args=[tenant.pk]) + "?section=contact"
    ).content.decode()
    assert name not in body
    assert 'name="remove_photo"' in body
    assert 'name="photo-clear"' not in body


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="photo-admin"))
    return client


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="photo-manager"))
    return client


def test_an_admin_adds_a_photo(as_admin, settings):
    tenant = make_tenant(username="ada")

    response = as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload("my face.png")},
    )

    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.photo
    assert tenant.photo.name.startswith("account_photos/")
    assert "my face" not in tenant.photo.name, "the client's filename is never used"
    assert (settings.MEDIA_ROOT / tenant.photo.name).exists()


def test_a_manager_may_see_but_not_set_a_tenant_photo(as_manager, settings):
    tenant = make_tenant(username="ada")
    give_photo(tenant)

    served = as_manager.get(reverse("manage:account-photo", args=[tenant.pk]))
    assert served.status_code == 200

    refused = as_manager.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload()},
    )
    assert refused.status_code == 403
    tenant.refresh_from_db()
    assert (settings.MEDIA_ROOT / tenant.photo.name).exists()

    # Closing a response sends request_finished, so it goes last.
    served.close()


def test_replacing_a_photo_deletes_the_previous_file(as_admin, settings):
    tenant = make_tenant(username="ada")
    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload("first.png")},
    )
    tenant.refresh_from_db()
    first = tenant.photo.name

    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload("second.png")},
    )
    tenant.refresh_from_db()

    assert tenant.photo.name != first
    assert not (settings.MEDIA_ROOT / first).exists()
    assert (settings.MEDIA_ROOT / tenant.photo.name).exists()


def test_removing_a_photo_deletes_the_file(as_admin, settings, client):
    tenant = make_tenant(username="ada")
    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload()},
    )
    tenant.refresh_from_db()
    stored = tenant.photo.name

    client.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"remove_photo": "on"},
    )
    tenant.refresh_from_db()

    assert not tenant.photo
    assert not (settings.MEDIA_ROOT / stored).exists()


def test_a_wrong_file_type_is_refused(as_admin):
    tenant = make_tenant(username="ada")

    response = as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": SimpleUploadedFile("photo.svg", b"<svg/>", content_type="image/svg+xml")},
        follow=True,
    )

    tenant.refresh_from_db()
    assert not tenant.photo
    assert b"JPEG, PNG, or WebP" in response.content


def test_an_oversized_photo_is_refused(as_admin, settings):
    settings.RHP_MAX_UPLOAD_MB = 1
    tenant = make_tenant(username="ada")

    response = as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": SimpleUploadedFile("huge.png", noisy_png_bytes(), content_type="image/png")},
        follow=True,
    )

    tenant.refresh_from_db()
    assert not tenant.photo
    assert b"larger than 1 MB" in response.content


def test_the_photo_is_served_to_staff(as_admin):
    tenant = make_tenant(username="ada")
    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload()},
    )

    response = as_admin.get(reverse("manage:account-photo", args=[tenant.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert "private" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    # Closing a response sends request_finished, so it goes last.
    response.close()


def test_an_account_without_a_photo_has_no_photo_url(as_admin):
    tenant = make_tenant(username="ada")

    assert as_admin.get(reverse("manage:account-photo", args=[tenant.pk])).status_code == 404


def test_a_tenant_is_served_their_own_photo(client):
    """The session decides which file is served; there is no id in the URL."""
    mine = make_tenant(username="ada")
    other = make_tenant(username="bob")
    mine_stored = give_photo(mine, "mine.png", size=(300, 300))
    other_stored = give_photo(other, "theirs.png", size=(400, 400))
    assert mine_stored != other_stored

    client.force_login(mine)
    response = client.get(reverse("accounts:photo"))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert int(response["Content-Length"]) == len(png_bytes((300, 300))), "it is my file"
    assert reverse("accounts:photo") == "/account/photo/"
    # Closing a response sends request_finished, so it goes last: nothing below
    # may touch the database.
    response.close()


def test_a_tenant_cannot_reach_a_photo_that_is_not_theirs(client):
    other = make_tenant(username="bob")
    give_photo(other, "theirs.png", size=(400, 400))
    mine = make_tenant(username="ada")
    client.force_login(mine)

    assert client.get(reverse("accounts:photo")).status_code == 404


def test_a_tenant_without_a_photo_is_told_nothing_is_there(client):
    tenant = make_tenant(username="ada")
    client.force_login(tenant)

    assert client.get(reverse("accounts:photo")).status_code == 404


def test_the_tenant_profile_shows_the_photo_form_and_uploads(client):
    tenant = make_tenant(username="ada")
    client.force_login(tenant)

    body = client.get(reverse("accounts:profile")).content.decode()
    assert "Save photo" in body
    assert reverse("accounts:photo-update") in body

    response = client.post(
        reverse("accounts:photo-update"),
        {"photo": photo_upload("mine.png")},
    )
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.photo
    served = client.get(reverse("accounts:photo"))
    assert served.status_code == 200
    served.close()


def test_a_manager_can_upload_their_own_photo(client):
    manager = make_manager(username="photo-manager")
    client.force_login(manager)

    response = client.post(reverse("accounts:photo-update"), {"photo": photo_upload()})

    assert response.status_code == 302
    manager.refresh_from_db()
    assert manager.photo


def test_an_admin_can_update_a_manager_photo(as_admin):
    manager = make_manager(username="photo-manager")

    response = as_admin.post(
        reverse("manage:account-photo-update", args=[manager.pk]),
        {"photo": photo_upload()},
    )

    assert response.status_code == 302
    manager.refresh_from_db()
    assert manager.photo


def test_the_account_page_shows_the_photo_and_the_upload_form(as_admin):
    tenant = make_tenant(username="ada")
    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload()},
    )

    body = as_admin.get(
        reverse("manage:account-detail", args=[tenant.pk]), {"section": "contact"}
    ).content.decode()

    assert reverse("manage:account-photo", args=[tenant.pk]) in body
    assert "Replace photo" in body


def test_a_manager_sees_but_cannot_edit_a_tenant_photo(as_manager):
    tenant = make_tenant(username="ada")
    give_photo(tenant)

    body = as_manager.get(
        reverse("manage:account-detail", args=[tenant.pk]), {"section": "contact"}
    ).content.decode()

    assert reverse("manage:account-photo", args=[tenant.pk]) in body
    assert "Only administrators can add or change another account" in body
    assert "Replace photo" not in body


def test_the_placeholder_is_drawn_when_there_is_no_photo(as_admin):
    tenant = make_tenant(username="ada")

    body = as_admin.get(
        reverse("manage:account-detail", args=[tenant.pk]), {"section": "contact"}
    ).content.decode()

    assert "No photo" in body, "the inline placeholder, not a broken image"
    assert 'class="person-image person-large"' in body


def test_the_tenant_list_shows_a_portrait_for_each_tenant(as_admin):
    tenant = make_tenant(username="ada", first_name="Ada")
    give_photo(tenant)

    body = as_admin.get(reverse("manage:account-list")).content.decode()

    assert reverse("manage:account-photo", args=[tenant.pk]) in body


def test_the_tenants_own_page_shows_their_photo(client):
    tenant = make_tenant(username="ada")
    give_photo(tenant)
    client.force_login(tenant)

    body = client.get(reverse("accounts:profile")).content.decode()

    assert reverse("accounts:photo") in body


def test_a_tenant_can_replace_a_photo_an_admin_supplied(as_admin, client, settings):
    tenant = make_tenant(username="ada")
    as_admin.post(
        reverse("manage:account-photo-update", args=[tenant.pk]),
        {"photo": photo_upload("admin-choice.png")},
    )
    tenant.refresh_from_db()
    admin_choice = tenant.photo.name

    client.force_login(tenant)
    response = client.post(
        reverse("accounts:photo-update"),
        {"photo": photo_upload("my-choice.png")},
    )

    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.photo.name != admin_choice
    assert (settings.MEDIA_ROOT / tenant.photo.name).exists()
    assert not (settings.MEDIA_ROOT / admin_choice).exists(), "the replaced file is removed"
