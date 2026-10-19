"""Banner photos: validation, storage, serving, and cleanup."""

import io
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from PIL import Image

from tests.factories import make_admin, make_manager, make_property, make_tenant

pytestmark = pytest.mark.django_db


def image_upload(name: str = "banner.png", fmt: str = "PNG", size=(800, 400)):
    """A real image, so Pillow's validation has something to read."""
    buffer = io.BytesIO()
    Image.new("RGB", size, "navy").save(buffer, format=fmt)
    content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def noisy_upload(name: str = "huge.png", size: tuple[int, int] = (1200, 1200)):
    """Random pixels compress badly, which makes an honest multi-megabyte file."""
    width, height = size
    image = Image.frombytes("RGB", size, os.urandom(width * height * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture
def as_manager(client):
    client.force_login(make_manager(username="banner-manager"))
    return client


@pytest.fixture
def as_admin(client):
    client.force_login(make_admin(username="banner-admin"))
    return client


def property_payload(property_, **overrides):
    payload = {
        "name": property_.name,
        "property_type": property_.property_type,
        "street": property_.street,
        "city": property_.city,
        "state": property_.state,
        "postal_code": property_.postal_code,
        "is_active": "on",
    }
    payload.update(overrides)
    return payload


def upload(client, property_, **overrides):
    return client.post(
        reverse("portfolio:property-update", args=[property_.pk]),
        property_payload(property_, **overrides),
    )


def test_uploading_a_banner_stores_a_randomised_name(as_manager, settings):
    property_ = make_property()

    response = upload(as_manager, property_, banner_image=image_upload("my photo.png"))

    property_.refresh_from_db()
    assert response.status_code == 302
    assert property_.banner_image
    assert property_.banner_image.name.startswith("property_banners/")
    assert "my photo" not in property_.banner_image.name
    assert (settings.MEDIA_ROOT / property_.banner_image.name).exists()


def test_each_upload_gets_its_own_name(as_manager):
    first = make_property(name="First")
    second = make_property(name="Second")

    upload(as_manager, first, banner_image=image_upload("same-name.png"))
    upload(as_manager, second, banner_image=image_upload("same-name.png"))

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.banner_image.name != second.banner_image.name


def test_an_oversized_image_is_refused(as_manager, settings):
    settings.RHP_MAX_UPLOAD_MB = 1
    property_ = make_property()

    response = upload(as_manager, property_, banner_image=noisy_upload())

    property_.refresh_from_db()
    assert response.status_code == 200
    assert not property_.banner_image
    assert b"larger than 1 MB" in response.content


def test_a_file_that_is_not_an_image_is_refused(as_manager):
    property_ = make_property()
    not_an_image = SimpleUploadedFile(
        "notes.pdf", b"%PDF-1.4 nothing here", content_type="application/pdf"
    )

    response = upload(as_manager, property_, banner_image=not_an_image)

    property_.refresh_from_db()
    assert response.status_code == 200
    assert not property_.banner_image


def test_replacing_a_banner_removes_the_previous_file(
    as_manager, settings, django_capture_on_commit_callbacks
):
    property_ = make_property()

    upload(as_manager, property_, banner_image=image_upload("first.png"))
    property_.refresh_from_db()
    first = property_.banner_image.name

    before_url = property_.banner_url
    with django_capture_on_commit_callbacks(execute=True):
        upload(as_manager, property_, banner_image=image_upload("second.png", size=(900, 450)))
    property_.refresh_from_db()
    second = property_.banner_image.name

    assert first != second
    assert property_.banner_url != before_url
    assert property_.banner_image.name not in property_.banner_url
    body = as_manager.get(
        reverse("portfolio:property-detail", args=[property_.pk])
    ).content.decode()
    assert property_.banner_url in body
    served = as_manager.get(property_.banner_url)
    try:
        with Image.open(io.BytesIO(b"".join(served.streaming_content))) as image:
            assert image.size == (900, 450)
    finally:
        served.close()
    assert not (settings.MEDIA_ROOT / first).exists()
    assert (settings.MEDIA_ROOT / second).exists()


def test_clear_button_deletes_photo_without_saving_unfinished_edits(
    as_manager, settings, django_capture_on_commit_callbacks
):
    property_ = make_property()
    upload(as_manager, property_, banner_image=image_upload())
    property_.refresh_from_db()
    stored = property_.banner_image.name

    original_name = property_.name
    with django_capture_on_commit_callbacks(execute=True):
        response = as_manager.post(
            reverse("portfolio:property-update", args=[property_.pk]),
            {"clear_banner": "1", "name": "", "street": "Unsaved edit"},
        )

    property_.refresh_from_db()
    assert not property_.banner_image
    assert property_.name == original_name
    assert property_.street != "Unsaved edit"
    assert response.status_code == 302
    assert not (settings.MEDIA_ROOT / stored).exists()


def test_clear_button_is_post_only_and_manager_only(client, as_manager):
    property_ = make_property()
    upload(as_manager, property_, banner_image=image_upload())
    url = reverse("portfolio:property-update", args=[property_.pk])
    assert as_manager.get(url, {"clear_banner": "1"}).status_code == 200
    client.force_login(make_tenant())
    assert client.post(url, {"clear_banner": "1"}).status_code == 403
    property_.refresh_from_db()
    assert property_.banner_image


def test_clear_rollback_keeps_the_saved_photo(as_manager, settings):
    property_ = make_property()
    upload(as_manager, property_, banner_image=image_upload())
    property_.refresh_from_db()
    stored = property_.banner_image.name
    with pytest.raises(RuntimeError), transaction.atomic():
        as_manager.post(
            reverse("portfolio:property-update", args=[property_.pk]), {"clear_banner": "1"}
        )
        raise RuntimeError("Rollback the test transaction")
    property_.refresh_from_db()
    assert property_.banner_image.name == stored
    assert (settings.MEDIA_ROOT / stored).exists()


def test_deleting_a_property_removes_its_banner(as_admin, settings):
    property_ = make_property()
    upload(as_admin, property_, banner_image=image_upload())
    property_.refresh_from_db()
    stored = property_.banner_image.name
    assert (settings.MEDIA_ROOT / stored).exists()

    as_admin.post(
        reverse("portfolio:property-delete", args=[property_.pk]),
        {"confirmation": "confirm delete"},
    )

    assert not (settings.MEDIA_ROOT / stored).exists()


def test_the_banner_is_served_to_staff(as_manager):
    property_ = make_property()
    upload(as_manager, property_, banner_image=image_upload())

    response = as_manager.get(reverse("portfolio:property-banner", args=[property_.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, no-cache"
    body = b"".join(response.streaming_content)
    response.close()  # the open file handle belongs to the response
    assert body


def test_a_property_without_a_banner_has_no_banner_url(as_manager):
    property_ = make_property()

    response = as_manager.get(reverse("portfolio:property-banner", args=[property_.pk]))

    assert response.status_code == 404


def test_a_tenant_cannot_fetch_a_banner(client):
    property_ = make_property(latitude=None)
    client.force_login(make_tenant(username="banner-tenant"))

    response = client.get(reverse("portfolio:property-banner", args=[property_.pk]))

    assert response.status_code == 403


def test_the_detail_page_shows_the_banner(as_manager):
    property_ = make_property()
    upload(as_manager, property_, banner_image=image_upload())

    body = as_manager.get(
        reverse("portfolio:property-detail", args=[property_.pk])
    ).content.decode()

    assert reverse("portfolio:property-banner", args=[property_.pk]) in body


def test_the_detail_page_has_no_banner_image_when_there_is_none(as_manager):
    property_ = make_property()

    body = as_manager.get(
        reverse("portfolio:property-detail", args=[property_.pk])
    ).content.decode()

    assert "Banner photo of" not in body


def test_the_form_offers_the_banner_field(as_manager):
    property_ = make_property()

    body = as_manager.get(
        reverse("portfolio:property-update", args=[property_.pk])
    ).content.decode()

    assert 'enctype="multipart/form-data"' in body
    assert 'name="banner_image"' in body
    assert 'name="coordinates"' in body
    assert 'name="remove_banner"' not in body
    assert 'name="banner_image-clear"' not in body
    assert 'name="clear_banner"' not in body

    upload(as_manager, property_, banner_image=image_upload())
    body = as_manager.get(
        reverse("portfolio:property-update", args=[property_.pk])
    ).content.decode()
    assert 'name="clear_banner"' in body
    assert 'form="clear-banner-form"' in body
    assert 'id="clear-banner-form"' in body
    assert "Clear banner photo" in body
