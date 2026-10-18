"""No DB required: the design prototype must not reach operational services."""

import json
import os
import socket
import subprocess
import sys
import threading
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

import pytest
from django.core import mail
from django.test import Client

from apps.responsibilities.services import allocate_monthly
from tools.design_prototype import data
from tools.design_prototype import settings as prototype_settings
from tools.design_prototype.views import back_path


def test_launcher_idle_connections_do_not_block_requests():
    from tools.design_prototype.__main__ import QuietHandler, ReviewServer

    timeouts = []

    class ObservedHandler(QuietHandler):
        def setup(self):
            super().setup()
            timeouts.append(self.request.gettimeout())

    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ready"]

    from wsgiref.simple_server import make_server

    with make_server(
        "127.0.0.1", 0, app, server_class=ReviewServer, handler_class=ObservedHandler
    ) as server:
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        idle = socket.create_connection(server.server_address, timeout=2)
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                assert response.read() == b"ready"
            assert timeouts and all(value == 10 for value in timeouts)
        finally:
            idle.close()
            server.shutdown()
            runner.join(timeout=2)


def test_empty_property_and_missing_unit_documents(prototype):
    data._snapshot = data.synthetic()
    data._snapshot["properties"].append(
        {"id": 3, "name": "Empty sample", "address": "300 Sample Road", "type": "Commercial"}
    )
    assert b"No units recorded" in prototype.get("/properties/?expanded=3").content
    assert b"No current tenancy" in prototype.get("/units/5/").content
    assert (
        b"Studio A \xe2\x80\x94 signed lease"
        not in prototype.get("/units/2/?section=documents").content
    )


@pytest.fixture
def prototype(settings):
    for key in (
        "ROOT_URLCONF",
        "MIDDLEWARE",
        "SESSION_ENGINE",
        "SESSION_COOKIE_NAME",
        "CACHES",
        "TEMPLATES",
        "MAILERS",
    ):
        setattr(settings, key, deepcopy(getattr(prototype_settings, key)))
    data._snapshot = None
    yield Client()
    data._snapshot = None


def payload(**changes):
    values = {
        "method": "custom",
        "remainder": "rhp",
        "amount_1": "33.20",
        "percent_1": "42.03",
        "basis_1": "amount",
        "amount_2": "45.80",
        "percent_2": "57.97",
        "basis_2": "amount",
    }
    values.update(changes)
    return values


def test_legacy_property_expansion_links_remain_addressable(prototype):
    closed = prototype.get("/properties/").content.decode()
    assert 'aria-expanded="true"' not in closed
    assert 'aria-current="page">All properties' in closed
    opened = prototype.get("/properties/?q=&expanded=1").content.decode()
    assert 'id="property-content-1"' in opened
    assert 'id="property-content-2"' not in opened
    assert "Studio A" in opened
    switched = prototype.get("/properties/?expanded=2").content.decode()
    assert 'id="property-content-2"' in switched
    assert 'id="property-content-1"' not in switched


def test_property_expansions_are_independent_and_remembered(prototype):
    both = prototype.get("/properties/?open=1,2").content.decode()
    assert 'id="property-content-1"' in both and 'id="property-content-2"' in both
    selected = prototype.get("/units/3/").content.decode()
    assert 'id="property-content-1"' in selected and 'id="property-content-2"' in selected
    closed = prototype.get("/units/3/?open=1").content.decode()
    assert 'id="property-content-1"' in closed and 'id="property-content-2"' not in closed
    # Explicitly closing the selected property's units is retained, not silently reopened.
    restored = prototype.get("/units/3/").content.decode()
    assert 'id="property-content-2"' not in restored
    history = prototype.get("/units/3/?open=1,2").content.decode()
    assert 'id="property-content-2"' in history
    bad = prototype.get("/properties/?open=999,invalid,1").content.decode()
    assert 'value="1"' in bad and "property-content-999" not in bad


def test_properties_has_one_navigator_without_duplicate_property_overview_links(prototype):
    root = prototype.get("/properties/").content.decode()
    detail = prototype.get("/units/1/?open=1,2").content.decode()
    for body in (root, detail):
        assert 'class="browser-property-header"' in body
        assert 'aria-label="Property and unit selection"' in body
        assert ">Property overview</a>" not in body
        assert "Open property workspace" not in body
    assert "Portfolio overview" in root
    assert "Current tenancy" in detail
    assert 'href="/properties/1/?' in detail  # The photo/name header selects its property.


@pytest.mark.parametrize(
    "path",
    [
        "/properties/",
        "/properties/1/",
        "/units/1/",
        "/tenants/1/",
        "/leases/1/",
        "/ledger/1/",
        "/maintenance/1/",
    ],
)
def test_navigation_tiers_replace_redundant_record_back_links(prototype, path):
    body = prototype.get(path).content.decode()
    assert "Back to results" not in body
    assert "Back to queue" not in body
    assert "Back to workspace" not in body
    assert "browser-scope" not in body
    assert 'aria-label="Portfolio views"' not in body
    # Portfolio-wide destinations remain in the primary navigation, not the middle tier.
    if path.startswith(("/properties/", "/units/")):
        navigator = body.split('aria-label="Property and unit selection"', 1)[1]
        navigator = navigator.split("</aside>", 1)[0]
        assert "All properties" not in navigator and "All units" not in navigator
        assert "All properties</a>" in body and "All units</a>" in body


def test_all_units_selection_retains_filter_return_and_tree_state(prototype):
    response = prototype.get("/units/?property=1&q=Studio&open=1,2")
    assert response.status_code == 200
    selected = next(u for u in response.context["unit_rows"] if u["id"] == 1)
    result = prototype.get(selected["workspace_url"])
    assert result.context["opened_properties"] == ["1", "2"]
    assert "property=1" in result.context["back"] and "q=Studio" in result.context["back"]
    assert b"Start a lease" in prototype.get("/units/5/?open=1,2").content


@pytest.mark.parametrize(
    "section", ["overview", "details", "maintenance", "recoveries", "documents"]
)
def test_unit_sections_keep_property_shell_and_scope(prototype, section):
    response = prototype.get(f"/units/1/?section={section}&back=/units/?q=Studio")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'aria-label="Property and unit selection"' in body
    assert 'href="/units/1/?section=' in body
    assert "Cedar House — inspection notes" not in body
    if section == "maintenance":
        assert "Water beneath kitchen sink" in body
        assert "Hallway light flickering" not in body
    if section == "recoveries":
        assert "Electricity" in body and "Water</h3>" not in body
    if section == "documents":
        assert "Studio A — signed lease" in body
    assert prototype.get("/units/1/?section=unknown").status_code == 404


def test_property_includes_common_area_not_other_property_units(prototype):
    body = prototype.get("/properties/1/?section=maintenance").content.decode()
    assert "Hallway light flickering" in body
    assert "Heating repair follow-up" not in body


def test_images_and_fallbacks_are_local_and_private_snapshot_has_no_fake_photos(prototype):
    body = prototype.get("/properties/?expanded=1").content.decode()
    assert "/assets/alder.png" in body and "/assets/studio.png" in body
    assert "image-fallback" in body
    for name in ("alder", "cedar", "studio", "portrait"):
        response = prototype.get(f"/assets/{name}.png")
        assert response.status_code == 200 and response["Content-Type"] == "image/png"
        response.close()
    data._snapshot = data.synthetic()
    body = prototype.get("/properties/").content.decode()
    assert "/assets/alder.png" not in body


def test_exact_linked_split_and_review_agree(prototype):
    values = payload(remainder="2", amount_1="55.00")
    result = prototype.post("/allocation/1/preview/", values).json()
    assert result["values"] == [
        {"id": 1, "amount": "55.00", "percent": "69.62"},
        {"id": 2, "amount": "24.00", "percent": "30.38"},
    ]
    review = prototype.post("/allocation/1/", {**values, "action": "review"})
    assert b"24.00" in review.content and b"55.00" in review.content
    assert b"Confirm allocation" in review.content
    linked = prototype.get("/allocation/1/?back=/units/1/?section=recoveries")
    assert b'href="/units/1/?section=recoveries"' in linked.content


def test_revision_copy_and_column_alignment_contract(prototype):
    dashboard = prototype.get("/").content.decode()
    assert "Your operations, in focus" not in dashboard
    assert "OPERATIONS DESK" not in dashboard
    assert "A person may have more" not in prototype.get("/tenants/").content.decode()
    assert "data-auto-filter" in prototype.get("/maintenance/").content.decode()
    assert 'class="number">Monthly rent' in prototype.get("/leases/").content.decode()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/properties/",
        "/properties/1/",
        "/units/",
        "/units/1/",
        "/tenants/",
        "/tenants/1/",
        "/leases/",
        "/leases/1/",
        "/ledger/",
        "/ledger/1/",
        "/recoveries/",
        "/allocation/1/",
        "/maintenance/",
        "/maintenance/1/",
        "/documents/",
        "/tenant/",
        "/preview/",
    ],
)
def test_all_workspaces_render_without_database(prototype, path):
    response = prototype.get(path)
    assert response.status_code == 200
    assert b"DESIGN PROTOTYPE" in response.content
    assert response["Cache-Control"] == "no-store"
    assert "form-action 'self'" in response["Content-Security-Policy"]


def test_edited_basis_controls_pair_and_matches_existing_service(prototype):
    first = prototype.post(
        "/allocation/1/preview/", payload(amount_1="40.00", amount_2="30.00")
    ).json()
    assert first["values"][0] == {"id": 1, "amount": "40.00", "percent": "50.63"}
    second = prototype.post(
        "/allocation/1/preview/", payload(basis_1="percent", percent_1="50", amount_2="30.00")
    ).json()
    assert second["values"][0]["amount"] == "39.50"
    third = prototype.post(
        "/allocation/1/preview/", payload(amount_1="40.01", percent_1="50", amount_2="30.00")
    ).json()
    assert third["values"][0]["amount"] == "40.01"
    existing = allocate_monthly(
        SimpleNamespace(monthly_total=Decimal("79")),
        units=[SimpleNamespace(pk=1, square_feet=840), SimpleNamespace(pk=2, square_feet=1160)],
        amounts={1: Decimal("40.01"), 2: Decimal("30")},
        percentages={},
        bases={1: "amount", 2: "amount"},
    )
    assert Decimal(third["values"][0]["amount"]) == existing.rows[0].amount


def test_explicit_recipient_does_not_replace_other_manual_amounts(prototype):
    values = {
        "method": "custom",
        "remainder": "5",
        "amount_3": "35",
        "amount_4": "30",
        "amount_5": "30",
        "basis_3": "amount",
        "basis_4": "amount",
        "basis_5": "amount",
    }
    result = prototype.post("/allocation/2/preview/", values).json()
    assert [r["amount"] for r in result["values"]] == ["35", "30", "35.00"]


def test_remainder_exclusion_vacancy_and_overallocation(prototype):
    response = prototype.post("/allocation/1/preview/", payload(remainder="2", amount_1="40"))
    assert response.json()["values"][1]["amount"] == "39.00"
    excluded = prototype.post(
        "/allocation/1/preview/", payload(basis_1="excluded", amount_1="")
    ).json()
    assert excluded["values"][0]["amount"] == "0.00"
    vacant = prototype.get("/allocation/1/?scenario=vacant").content
    assert b"Vacant" in vacant and b"45.80" in vacant
    over = prototype.post("/allocation/1/preview/", payload(amount_1="70", amount_2="40")).json()
    assert not over["valid"] and "Over-allocated by $31.00" in over["summary"]
    assert 'role="button"' not in over["summary"]


def test_zero_missing_size_foreign_recipient_and_nonfinite(prototype):
    zero = prototype.get("/allocation/1/?scenario=zero")
    assert b"No amount to allocate" in zero.content
    missing = prototype.post(
        "/allocation/1/preview/", payload(scenario="missing-size", method="size")
    ).json()
    assert not missing["valid"] and "Record square footage" in missing["summary"]
    assert not prototype.post("/allocation/1/preview/", payload(remainder="999")).json()["valid"]
    assert not prototype.post("/allocation/1/preview/", payload(amount_1="NaN")).json()["valid"]


def test_plain_form_review_back_confirmation_and_stale_review(prototype):
    values = payload(action="review", amount_1="40", amount_2="30")
    assert b"Monthly allocation changes" in prototype.post("/allocation/1/", values).content
    assert (
        b"Prototype only"
        in prototype.post(
            "/allocation/1/", payload(action="save", amount_1="40", amount_2="30")
        ).content
    )
    assert (
        b"Allocation confirmation preview"
        not in prototype.post("/allocation/1/", payload(action="save")).content
    )
    prototype.post("/allocation/1/", values)
    assert (
        b"Allocation confirmation preview"
        not in prototype.post("/allocation/1/", payload(action="save", amount_1="20")).content
    )
    back = prototype.post("/allocation/1/", payload(action="back", amount_1="40", amount_2="30"))
    assert b'value="40"' in back.content
    assert b"Saving" not in back.content
    assert data.synthetic()["bills"][0]["amounts"]["1"] == "33.20"


def test_locked_cycle_refuses_preview_and_completion(prototype):
    assert prototype.post("/allocation/1/preview/", payload(scenario="locked")).status_code == 409
    response = prototype.post("/allocation/1/", payload(scenario="locked", action="save"))
    assert b"history is locked" in response.content
    assert "drafts" not in prototype.session


def test_status_simulation_and_reset(prototype):
    result = prototype.post(
        "/maintenance/1/?back=/maintenance/?q=Water", {"status": "Acknowledged"}
    )
    assert "Prototype only—no RHP records changed." in result.content.decode()
    assert b"Acknowledged" in prototype.get("/maintenance/").content
    assert b"Give a reason" in prototype.post("/maintenance/1/", {"status": "Open"}).content
    assert b"Enter a date" in prototype.post("/maintenance/1/", {"status": "Scheduled"}).content
    assert prototype.get("/reset/").status_code == 405
    assert prototype.post("/reset/").status_code == 302
    assert "work" not in prototype.session


def test_tenant_sample_has_no_staff_evidence_or_other_accounts(prototype):
    body = prototype.get("/tenant/").content
    assert b"Alex Morgan" not in body  # sample identifies the tenancy, not a staff directory
    assert b"Jordan Lee" not in body and b"Taylor Reed" not in body
    assert b"Internal notes" not in body and b"Costs, recharges" not in body


def test_csrf_assets_paths_and_no_mail(prototype):
    strict = Client(enforce_csrf_checks=True)
    assert strict.post("/maintenance/1/", {"status": "Completed"}).status_code == 403
    asset = prototype.get("/assets/prototype.css")
    assert asset.status_code == 200
    asset.close()
    assert prototype.get("/assets/snapshot.json").status_code == 404
    assert prototype.get("/manage/ledger/").status_code == 404
    assert prototype.get("/properties/999/").status_code == 404
    with pytest.raises(RuntimeError, match="cannot send email"):
        mail.send_mail("test", "body", "rhp@example.test", ["tenant@example.test"])
    assert back_path("//example.com", "/") == "/"
    assert back_path("https://example.com", "/") == "/"
    assert back_path("/maintenance/?q=Water", "/") == "/maintenance/?q=Water"


def test_dedicated_process_has_dummy_database_and_no_live_routes():
    script = """import django; django.setup()
from django.conf import settings
from django.test import Client
from django.db import connection
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.dummy'
assert Client().get('/').status_code == 200
assert Client().get('/allocation/1/').status_code == 200
try: connection.cursor()
except Exception: pass
else: raise AssertionError('Database unexpectedly available')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "tools.design_prototype.settings"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_snapshot_schema_and_size_validation(tmp_path):
    path = tmp_path / "private.json"
    path.write_text(json.dumps({"schema": 1, **data.synthetic()}))
    data.load_snapshot(path)
    assert data.dataset()["properties"][0]["name"] == "Alder Court"
    path.write_text(json.dumps({"schema": 1, **data.synthetic(), "password": "not permitted"}))
    with pytest.raises(ValueError):
        data.load_snapshot(path)
    data._snapshot = None


def test_no_production_asset_or_url_imports():
    source = Path("config/urls.py").read_text() + Path("templates/base.html").read_text()
    assert "design_prototype" not in source


@pytest.mark.django_db(transaction=True)
def test_export_queries_are_database_read_only():
    from django.db import connection

    from tools.design_prototype.export import snapshot_data

    statements = []

    def capture(execute, sql, params, many, context):
        statements.append(sql.strip().upper())
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture):
        result = snapshot_data()
    assert "SET TRANSACTION READ ONLY" in statements
    assert all(s.startswith(("BEGIN", "SET TRANSACTION READ ONLY", "SELECT")) for s in statements)
    assert result["schema"] == 1
    assert set(result) == {
        "schema",
        "source",
        "properties",
        "units",
        "tenants",
        "leases",
        "bills",
        "documents",
    }


def test_export_file_is_private_and_outside_repository(tmp_path, monkeypatch):
    from tools.design_prototype import export

    monkeypatch.setattr(export, "snapshot_data", lambda: {"schema": 1, **data.synthetic()})
    monkeypatch.setattr(export.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    target = export.export_snapshot()
    assert target.stat().st_mode & 0o777 == 0o600
    assert not target.is_relative_to(Path.cwd())
