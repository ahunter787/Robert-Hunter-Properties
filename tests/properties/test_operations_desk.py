"""E11: real navigation, scoped projections and optional private unit photos."""

from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse

from apps.documents.models import Document
from apps.maintenance import services
from apps.properties.models import Unit
from tests.factories import (
    make_admin,
    make_lease,
    make_maintenance,
    make_manager,
    make_property,
    make_tenant,
    make_unit,
)
from tests.properties.test_banner import image_upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(client):
    user = make_manager()
    client.force_login(user)
    return user


def test_sidebar_order_and_no_redundant_middle_navigation(client, manager):
    unit = make_unit()
    response = client.get(reverse("portfolio:unit-detail", args=[unit.pk]))
    assert response.status_code == 200
    items = response.context["portal_nav"]
    assert [i["label"] for i in items] == [
        "Dashboard",
        "Properties",
        "Tenants",
        "People",
        "Leases",
        "Timeline",
        "Insurance",
        "Rent & Payments",
        "Accounting",
        "Expense recoveries",
        "Maintenance",
        "Communications",
        "Documents",
    ]
    body = response.content.decode()
    middle = body.split('aria-label="Property and unit selection"')[1].split("</aside>")[0]
    assert "All properties" not in middle and "All units" not in middle
    assert "Back to" not in body
    assert not any(i["active"] for i in items if i["key"] != "properties")


def test_independent_expansion_deep_links_and_invalid_state(client, manager):
    a, b = make_unit(), make_unit()
    url = reverse("portfolio:unit-detail", args=[b.pk])
    opened = f"{a.property_id},{b.property_id}"
    response = client.get(url, {"open": opened, "q": "Loft", "page": "2"})
    rows = response.context["workspace_properties"]
    assert all(p.workspace_open for p in rows)
    assert all("q=Loft" in p.workspace_url for p in rows)
    assert all("page=2" in p.workspace_url for p in rows)
    response = client.get(url, {"open": str(a.property_id)})
    assert [p.pk for p in response.context["workspace_properties"] if p.workspace_open] == [
        a.property_id
    ]
    response = client.get(
        url, {"open": "evil,999999999999999999999999", "section": "https://bad.test"}
    )
    assert response.context["workspace_section"] == "overview"
    assert not any(p.workspace_open for p in response.context["workspace_properties"])


@pytest.mark.parametrize(
    "section", ["overview", "details", "maintenance", "documents", "recoveries"]
)
def test_local_sections_remain_in_properties(client, manager, section):
    unit = make_unit()
    response = client.get(reverse("portfolio:unit-detail", args=[unit.pk]), {"section": section})
    assert response.status_code == 200
    assert response.context["portal_active"] == "properties"
    assert response.context["workspace_section"] == section
    assert all("/manage/units/" in t["url"] for t in response.context["workspace_tabs"])


def test_related_documents_and_work_are_scoped(client, manager):
    a, b = make_unit(), make_unit()
    first, second = make_lease(a), make_lease(b)
    for lease, title in [(first, "Own file"), (second, "Unrelated file")]:
        Document.objects.create(title=title, lease=lease, file="test.pdf")
        services.create_request(
            actor=manager,
            property=lease.unit.property,
            unit=lease.unit,
            title=title,
            description="Synthetic",
            category="general",
        )
    for section, key in [
        ("documents", "workspace_documents"),
        ("maintenance", "workspace_requests"),
    ]:
        response = client.get(reverse("portfolio:unit-detail", args=[a.pk]), {"section": section})
        assert [r.title for r in response.context[key]] == ["Own file"]
        assert "Unrelated file" not in response.content.decode()


def test_empty_property_and_read_only_navigation(client, manager):
    prop = make_property()
    before = Unit.objects.count()
    for section in ("overview", "details", "documents", "maintenance", "recoveries"):
        assert (
            client.get(
                reverse("portfolio:property-detail", args=[prop.pk]), {"section": section}
            ).status_code
            == 200
        )
    assert Unit.objects.count() == before


@pytest.mark.parametrize("factory", [make_tenant, make_maintenance])
def test_role_shell_does_not_grant_portfolio_access(client, factory):
    user = factory()
    client.force_login(user)
    response = client.get(reverse("accounts:profile"))
    assert not any(i["key"] == "properties" for i in response.context["portal_nav"])
    assert client.get(reverse("portfolio:property-list")).status_code == 403
    assert client.get(reverse("responsibilities:overview")).status_code == 403


def photo_payload(unit, **values):
    return {
        "property": unit.property_id,
        "identifier": unit.identifier,
        "is_active": "on",
        **values,
    }


def test_photo_upload_replace_remove_after_commit(
    client, manager, settings, django_capture_on_commit_callbacks
):
    unit = make_unit()
    url = reverse("portfolio:unit-update", args=[unit.pk])
    assert (
        client.post(url, photo_payload(unit, photo=image_upload("private name.png"))).status_code
        == 302
    )
    unit.refresh_from_db()
    old = unit.photo.name
    assert old.startswith("unit_photos/") and "private name" not in old
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url, photo_payload(unit, photo=image_upload())).status_code == 302
        assert (settings.MEDIA_ROOT / old).exists()
    assert not (settings.MEDIA_ROOT / old).exists()
    unit.refresh_from_db()
    old = unit.photo.name
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url, photo_payload(unit, remove_photo="on")).status_code == 302
    unit.refresh_from_db()
    assert not unit.photo and not (settings.MEDIA_ROOT / old).exists()


@pytest.mark.parametrize("invalid", ["format", "conflict", "pixels", "size"])
def test_photo_validation(client, manager, settings, invalid):
    unit = make_unit()
    upload = image_upload()
    values = {"photo": upload}
    if invalid == "format":
        values["photo"] = SimpleUploadedFile(
            "bad.svg", b"<svg></svg>", content_type="image/svg+xml"
        )
    elif invalid == "conflict":
        values["remove_photo"] = "on"
    elif invalid == "pixels":
        values["photo"] = image_upload(size=(6001, 1))
    else:
        settings.RHP_MAX_UPLOAD_MB = 0
    response = client.post(
        reverse("portfolio:unit-update", args=[unit.pk]), photo_payload(unit, **values)
    )
    assert response.status_code == 200
    assert response.context["form"].errors
    unit.refresh_from_db()
    assert not unit.photo


def test_failed_database_write_cleans_new_photo(client, manager, settings):
    unit = make_unit()
    with patch.object(Unit, "save", side_effect=RuntimeError("simulated failure")):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("portfolio:unit-update", args=[unit.pk]),
                photo_payload(unit, photo=image_upload()),
            )
    assert list(Path(settings.MEDIA_ROOT).glob("unit_photos/*")) == []


def test_failed_transaction_after_photo_write_keeps_previous(client, manager, settings):
    unit = make_unit(photo=image_upload())
    old = unit.photo.name
    with patch("apps.properties.forms.UnitForm._save_m2m", side_effect=RuntimeError("after save")):
        with pytest.raises(RuntimeError):
            client.post(
                reverse("portfolio:unit-update", args=[unit.pk]),
                photo_payload(unit, photo=image_upload()),
            )
    unit.refresh_from_db()
    assert unit.photo.name == old
    assert [p.name for p in (settings.MEDIA_ROOT / "unit_photos").iterdir()] == [Path(old).name]


def test_photo_authorization_and_tenant_lease_resolution(client, manager):
    tenant = make_tenant()
    unit = make_unit(photo=image_upload())
    lease = make_lease(unit, tenants=[tenant])
    staff_url = reverse("portfolio:unit-photo", args=[unit.pk])
    response = client.get(staff_url)
    assert response.status_code == 200 and response["Cache-Control"].startswith("private")
    assert b"".join(response.streaming_content)
    client.force_login(tenant)
    assert client.get(staff_url).status_code == 403
    own = reverse("tenant_portfolio:photo", args=["unit"])
    response = client.get(own, {"unit": 999999})
    assert response.status_code == 200
    assert b"".join(response.streaming_content)
    lease.status = "ENDED"
    lease.save()
    response = client.get(own)
    assert response.status_code == 200
    assert b"".join(response.streaming_content)
    client.force_login(make_tenant(username="unrelated"))
    assert client.get(own).status_code == 404
    client.force_login(make_maintenance())
    assert client.get(staff_url).status_code == 403
    client.logout()
    assert client.get(staff_url).status_code == 302


def test_missing_photo_and_admin_delete_cleanup(
    client, settings, django_capture_on_commit_callbacks
):
    client.force_login(make_admin())
    unit = make_unit()
    assert client.get(reverse("portfolio:unit-photo", args=[unit.pk])).status_code == 404
    unit.photo = "unit_photos/missing.png"
    unit.save()
    assert client.get(reverse("portfolio:unit-photo", args=[unit.pk])).status_code == 404
    unit.photo = image_upload()
    unit.save()
    old = unit.photo.name
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("portfolio:unit-delete", args=[unit.pk]))
        assert (settings.MEDIA_ROOT / old).exists()
    assert not (settings.MEDIA_ROOT / old).exists()


def test_rolled_back_deletion_keeps_photo(settings, django_capture_on_commit_callbacks):
    unit = make_unit(photo=image_upload())
    old = unit.photo.name
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            unit.delete()
            raise RuntimeError("cancel deletion")
    assert (settings.MEDIA_ROOT / old).exists()
