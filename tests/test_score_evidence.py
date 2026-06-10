"""FIX 3: scores carry evidence — which keywords matched per dimension,
persisted via score_evidence_json and exposed in the API schema.
"""
from __future__ import annotations

import json
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
from job_finder.scoring.core import score_job_basic  # noqa: E402

_JD = (
    "Build pipelines with Python and Airflow. "
    "We offer equity and RSU grants to every engineer."
)
_RESUME = "Python data engineer."
_CFG = {
    "keywords": {
        "technical": ["python", "airflow", "spark", "kafka", "dbt", "snowflake", "terraform"],
        "leadership": ["mentor", "team lead"],
        "high_comp_signals": ["equity", "rsu", "signing bonus"],
    }
}

_DIMENSIONS = (
    "technical_skills",
    "leadership_signal",
    "platform_building",
    "company_trajectory",
    "culture_fit",
    "comp_potential",
)


# ── evidence shape from the scorer ────────────────────────────────────────

def test_score_evidence_lists_exact_matches_per_dimension():
    result = score_job_basic(_JD, _RESUME, config=_CFG)
    evidence = result["score_evidence"]

    assert set(evidence["technical_skills"]["matched"]) == {"python", "airflow"}
    assert evidence["technical_skills"]["missing_top"] == [
        "spark", "kafka", "dbt", "snowflake", "terraform",
    ]
    assert set(evidence["comp_potential"]["matched"]) == {"equity", "rsu"}
    assert "signing bonus" in evidence["comp_potential"]["missing_top"]


def test_score_evidence_covers_keyword_dimensions_with_capped_missing():
    result = score_job_basic(_JD, _RESUME, config=_CFG)
    evidence = result["score_evidence"]
    for dim in _DIMENSIONS:
        assert dim in evidence
        assert isinstance(evidence[dim]["matched"], list)
        assert isinstance(evidence[dim]["missing_top"], list)
        assert len(evidence[dim]["missing_top"]) <= 5


# ── DB round trip ─────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


_EVIDENCE = {
    "technical_skills": {"matched": ["python"], "missing_top": ["spark", "kafka"]},
    "comp_potential": {"matched": ["equity"], "missing_top": []},
}


def test_save_application_round_trips_score_evidence(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/1",
        overall_score=72.0,
        score_evidence=_EVIDENCE,
    )
    assert rec is not None
    assert json.loads(rec.score_evidence_json) == _EVIDENCE

    fetched = db.get_all_applications()
    assert len(fetched) == 1
    assert fetched[0].score_evidence == _EVIDENCE


def test_save_application_defaults_to_empty_evidence(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/2",
    )
    assert rec is not None
    assert (rec.score_evidence_json or "") == ""
    assert rec.score_evidence is None


def test_migration_adds_score_evidence_column(tmp_path):
    import sqlite3

    path = os.path.join(str(tmp_path), "job_tracker.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE applications ("
        "id INTEGER PRIMARY KEY, job_title VARCHAR(500), "
        "company VARCHAR(300), job_url VARCHAR(2000))"
    )
    conn.commit()
    conn.close()

    database.init_db(path)
    try:
        from sqlalchemy import inspect

        cols = {c["name"] for c in inspect(database._engine).get_columns("applications")}
        assert "score_evidence_json" in cols
    finally:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()


# ── API schema exposure ───────────────────────────────────────────────────

def test_to_response_serializer_includes_score_evidence(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/4",
        overall_score=70.0,
        score_evidence=_EVIDENCE,
    )

    from app.api.applications import _to_response

    resp = _to_response(rec)
    assert resp.score_evidence == _EVIDENCE
    assert resp.model_dump()["score_evidence"] == _EVIDENCE


def test_application_response_schema_exposes_score_evidence(db):
    rec = db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/3",
        overall_score=70.0,
        score_evidence=_EVIDENCE,
    )

    from app.schemas.application import ApplicationResponse

    assert "score_evidence" in ApplicationResponse.model_fields
    resp = ApplicationResponse(
        id=rec.id,
        job_title=rec.job_title,
        company=rec.company,
        score_evidence=rec.score_evidence,
    )
    assert resp.score_evidence == _EVIDENCE
    assert resp.model_dump()["score_evidence"] == _EVIDENCE


# ── API endpoint round trip ───────────────────────────────────────────────

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


def test_applications_api_returns_score_evidence(api_client):
    """Producer (save_application) -> API serializer -> JSON the frontend reads."""
    client, jf_db = api_client
    rec = jf_db.save_application(
        job_title="Data Engineer",
        company="Acme",
        job_url="https://example.com/jobs/5",
        overall_score=70.0,
        score_evidence=_EVIDENCE,
    )

    detail = client.get(f"/api/v1/applications/{rec.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["score_evidence"] == _EVIDENCE

    listing = client.get("/api/v1/applications")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert items and items[0]["score_evidence"] == _EVIDENCE
