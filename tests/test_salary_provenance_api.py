"""Review fix: salary provenance must survive the applications API boundary.

The branch persists ``salary_source`` ('reported' | 'parsed_from_description'
| NULL) and the frontend renders an "estimated from description" badge from
``app.salary_source`` — but the Pydantic response schema never declared the
field, so it was silently dropped and the badge was dead code. These tests
pin the contract: salary_source round-trips DB -> serializer -> JSON, and the
companion confidence fields the frontend types declare (date_confidence,
work_type_confidence) are present in the payload.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.models import database  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def test_application_response_declares_provenance_fields():
    from app.schemas.application import ApplicationResponse

    for field in ("salary_source", "date_confidence", "work_type_confidence"):
        assert field in ApplicationResponse.model_fields, field


def test_to_response_serializes_salary_source(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/1",
        salary_min=140000.0,
        salary_max=170000.0,
        salary_source="parsed_from_description",
    )

    from app.api.applications import _to_response

    resp = _to_response(rec)
    assert resp.salary_source == "parsed_from_description"
    assert resp.model_dump()["salary_source"] == "parsed_from_description"


def test_to_response_salary_source_none_when_unknown(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/2",
    )

    from app.api.applications import _to_response

    assert _to_response(rec).salary_source is None


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORKSPACE_STORAGE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    for module_name in list(sys.modules):
        if (
            module_name == "app"
            or module_name.startswith("app.")
            or module_name == "job_finder.models"
            or module_name.startswith("job_finder.models.")
        ):
            sys.modules.pop(module_name, None)

    backend_db = importlib.import_module("app.models.database")
    backend_db.init_db(str(db_path))
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(db_path))
    app_main = importlib.import_module("app.main")

    with TestClient(app_main.app) as client:
        yield client, jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def test_applications_api_returns_salary_source(api_client):
    """save_application -> API serializer -> the JSON the badge reads."""
    client, jf_db = api_client
    rec = jf_db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/3",
        salary_min=140000.0,
        salary_max=170000.0,
        salary_source="parsed_from_description",
    )

    detail = client.get(f"/api/v1/applications/{rec.id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["salary_source"] == "parsed_from_description"
    # Declared by the frontend ApplicationBase type — must exist in the payload
    # (null until a value is persisted) instead of vanishing from the contract.
    assert "date_confidence" in payload
    assert "work_type_confidence" in payload

    listing = client.get("/api/v1/applications")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert items and items[0]["salary_source"] == "parsed_from_description"
