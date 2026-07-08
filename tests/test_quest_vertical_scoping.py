"""Structural career scoping for quest verticals.

Every legacy consumer of the applications table must go through
scoped_applications() and default to career, so quest rows (vertical camera,
study, lens, party) are invisible to and untouchable by career machinery
unless a caller opts in. Each test here inserts a quest row, runs one
consumer, and proves the row is unaffected.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
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


def _save_camera_row(db, **overrides):
    kwargs = dict(
        job_title="Audience seat: The Late Show",
        company="1iota / CBS",
        location="New York, NY",
        job_url="https://1iota.com/show/536",
        source="1iota",
        vertical="camera",
    )
    kwargs.update(overrides)
    return db.save_application(**kwargs)


def _camera_rows(db):
    session = db.get_session()
    try:
        return database.scoped_applications(session, ["camera"]).all()
    finally:
        db._close_session()


# ---------------------------------------------------------------------------
# save_application threading


def test_save_application_defaults_to_career(db):
    rec = db.save_application(job_title="Data Engineer", company="Acme")
    assert rec.vertical == "career"
    assert rec.is_rolling is False
    assert rec.first_quest_ok is False
    assert (rec.quest_json or "") == ""


def test_save_application_threads_vertical_and_quest_fields(db):
    rec = _save_camera_row(
        db,
        event_start=datetime(2026, 7, 14, 16, 0),
        event_end=datetime(2026, 7, 14, 19, 0),
        first_quest_ok=True,
        quest_json='{"headcount": 250, "age_min": 16}',
    )
    assert rec.vertical == "camera"
    assert rec.event_start == datetime(2026, 7, 14, 16, 0)
    assert rec.event_end == datetime(2026, 7, 14, 19, 0)
    assert rec.first_quest_ok is True
    assert rec.quest_json == '{"headcount": 250, "age_min": 16}'


def test_save_application_rejects_unknown_vertical(db):
    with pytest.raises(ValueError):
        db.save_application(job_title="X", company="Y", vertical="bogus")
    # 'personal' is a UI-only log lane, never a stored applications vertical.
    with pytest.raises(ValueError):
        db.save_application(job_title="X", company="Y", vertical="personal")


def test_fuzzy_dedup_never_merges_quest_into_career(db):
    # A camera row exists with no URL; a career save with the same normalized
    # company+title must create a NEW row instead of merging into the quest.
    _save_camera_row(db, job_url="", job_title="Focus group", company="Fieldwork Chicago")
    career = db.save_application(
        job_title="Focus group", company="Fieldwork Chicago", vertical="career",
    )
    assert career.vertical == "career"
    rows = db.get_all_applications(verticals=["career", "camera"])
    assert len(rows) == 2


def test_fuzzy_dedup_never_merges_career_into_quest(db):
    db.save_application(job_title="Focus group", company="Fieldwork Chicago")
    quest = _save_camera_row(
        db, job_url="", job_title="Focus group", company="Fieldwork Chicago",
    )
    assert quest.vertical == "camera"
    rows = db.get_all_applications(verticals=["career", "camera"])
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# src-level consumers


def test_get_all_applications_defaults_to_career(db):
    db.save_application(job_title="Data Engineer", company="Acme")
    _save_camera_row(db)
    rows = db.get_all_applications()
    assert [r.vertical for r in rows] == ["career"]
    assert len(db.get_all_applications(verticals=["camera"])) == 1


def test_purge_locations_never_deletes_quest_rows(db):
    db.save_application(
        job_title="Data Engineer", company="Acme",
        location="New York, NY", job_url="https://example.com/jobs/1",
    )
    _save_camera_row(db)
    deleted = db.purge_non_matching_locations(preferred_cities=["San Francisco"])
    assert deleted == 1
    assert db.get_all_applications() == []
    assert len(_camera_rows(db)) == 1


def test_purge_roles_never_deletes_quest_rows(db):
    db.save_application(
        job_title="Barista", company="Acme", job_url="https://example.com/jobs/2",
    )
    _save_camera_row(db)
    deleted = db.purge_non_matching_roles(["data engineer"])
    assert deleted == 1
    assert db.get_all_applications() == []
    assert len(_camera_rows(db)) == 1


def test_backfill_scores_never_scores_quest_rows(db, monkeypatch):
    monkeypatch.setattr(
        "job_finder.tools.resume_parser_tool.parse_resume",
        lambda *args, **kwargs: "python sql etl data engineering resume",
    )
    career = db.save_application(
        job_title="Data Engineer", company="Acme",
        description="python sql etl pipelines",
        job_url="https://example.com/jobs/3",
    )
    quest = _save_camera_row(db)
    assert career.overall_score is None
    scored = db.backfill_scores()
    assert scored == 1
    rows = {r.id: r for r in db.get_all_applications(verticals=["career", "camera"])}
    assert rows[career.id].overall_score is not None
    assert rows[quest.id].overall_score is None


def test_backfill_company_types_never_classifies_quest_rows(db, monkeypatch):
    monkeypatch.setattr(
        "job_finder.company_classifier.classify_company",
        lambda *args, **kwargs: "Big Tech",
    )
    career = db.save_application(
        job_title="Data Engineer", company="Google",
        job_url="https://example.com/jobs/4",
    )
    quest = _save_camera_row(db, company="Google")
    updated = db.backfill_company_types()
    assert updated == 1
    rows = {r.id: r for r in db.get_all_applications(verticals=["career", "camera"])}
    assert rows[career.id].company_type == "Big Tech"
    assert rows[quest.id].company_type == "Unknown"


# ---------------------------------------------------------------------------
# API-level consumers


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


def _seed_pair(jf_db):
    """One scored career row + one unscored camera quest row."""
    career = jf_db.save_application(
        job_title="Data Engineer", company="Acme",
        location="New York, NY", job_url="https://example.com/jobs/1",
        overall_score=80.0,
    )
    quest = jf_db.save_application(
        job_title="Audience seat: The Late Show", company="1iota / CBS",
        location="New York, NY", job_url="https://1iota.com/show/536",
        source="1iota", vertical="camera",
    )
    return career, quest


def test_list_applications_default_hides_quest_rows(api_client):
    client, jf_db = api_client
    _seed_pair(jf_db)
    resp = client.get("/api/v1/applications")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] == 1
    assert [item["vertical"] for item in payload["items"]] == ["career"]


def test_list_applications_vertical_param(api_client):
    client, jf_db = api_client
    _seed_pair(jf_db)

    camera = client.get("/api/v1/applications", params={"vertical": "camera"}).json()
    assert camera["total"] == 1
    assert camera["items"][0]["vertical"] == "camera"
    assert camera["items"][0]["job_title"] == "Audience seat: The Late Show"

    both = client.get(
        "/api/v1/applications", params={"vertical": "career,camera"}
    ).json()
    assert both["total"] == 2
    assert {item["vertical"] for item in both["items"]} == {"career", "camera"}


def test_list_applications_rejects_unknown_vertical(api_client):
    client, _jf_db = api_client
    resp = client.get("/api/v1/applications", params={"vertical": "bogus"})
    assert resp.status_code == 400
    resp = client.get("/api/v1/applications", params={"vertical": "personal"})
    assert resp.status_code == 400


def test_default_sort_cannot_flood_classic_page_with_unscored_quests(api_client):
    """Default sort is overall_score desc NULLSFIRST. Without career scoping an
    unscored quest row would float to the very top of the classic page."""
    client, jf_db = api_client
    _seed_pair(jf_db)
    resp = client.get("/api/v1/applications", params={"page": 1})
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["job_title"] == "Data Engineer"
    assert all(item["vertical"] == "career" for item in payload["items"])


def test_csv_export_excludes_quest_rows(api_client):
    client, jf_db = api_client
    _seed_pair(jf_db)
    resp = client.get("/api/v1/applications/export/csv")
    assert resp.status_code == 200
    assert "Acme" in resp.text
    assert "1iota" not in resp.text


def test_analytics_exclude_quest_rows(api_client):
    client, jf_db = api_client
    _seed_pair(jf_db)
    from app.models.database import get_db
    from app.services import analytics_service

    db = next(get_db())
    try:
        stats = analytics_service.get_dashboard_stats(db)
        assert stats["total_jobs"] == 1
        assert stats["avg_score"] == 80.0
        sources = {row["label"] for row in analytics_service.get_source_breakdown(db)}
        assert "1iota" not in sources
        companies = {row["company"] for row in analytics_service.get_top_companies(db)}
        assert "1iota / CBS" not in companies
        types = analytics_service.get_company_types(db)
        assert sum(row["count"] for row in types) == 1
    finally:
        db.close()


def test_deduplicate_leaves_quest_rows_untouched(api_client):
    client, jf_db = api_client
    session = jf_db.get_session()
    try:
        shared = dict(
            job_title="Focus group", company="Fieldwork Chicago",
            location="Chicago", description="Talk about snacks for an hour.",
        )
        session.add(jf_db.ApplicationRecord(**shared, vertical="career"))
        session.add(jf_db.ApplicationRecord(**shared, vertical="career"))
        session.add(jf_db.ApplicationRecord(**shared, vertical="camera"))
        session.commit()
    finally:
        jf_db._close_session()

    resp = client.post("/api/v1/applications/deduplicate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed"] == 1

    camera = client.get("/api/v1/applications", params={"vertical": "camera"}).json()
    assert camera["total"] == 1
    career = client.get("/api/v1/applications").json()
    assert career["total"] == 1


def test_purge_locations_endpoint_never_deletes_quest_rows(api_client, monkeypatch):
    client, jf_db = api_client
    _seed_pair(jf_db)
    monkeypatch.setattr(
        "job_finder.pipeline._load_search_config",
        lambda profile=None: {
            "location_preferences": {
                "filter_enabled": True,
                "preferred_cities": ["San Francisco"],
                "include_remote": True,
            }
        },
    )
    resp = client.post("/api/v1/applications/purge-locations")
    assert resp.status_code == 200, resp.text
    assert resp.json()["purged"] == 1

    camera = client.get("/api/v1/applications", params={"vertical": "camera"}).json()
    assert camera["total"] == 1
    career = client.get("/api/v1/applications").json()
    assert career["total"] == 0


# ---------------------------------------------------------------------------
# status lifecycle widening


def test_status_widening_accepts_new_values(api_client):
    client, jf_db = api_client
    career, quest = _seed_pair(jf_db)
    for app_id, status in [
        (career.id, "clipped"),
        (career.id, "reviewed"),
        (quest.id, "booked"),
        (quest.id, "attended"),
        (quest.id, "paid_out"),
        (quest.id, "expired"),
        (career.id, "applied"),
    ]:
        resp = client.patch(
            f"/api/v1/applications/{app_id}/status", json={"status": status}
        )
        assert resp.status_code == 200, f"{status}: {resp.text}"
        assert resp.json()["status"] == status


def test_status_widening_still_rejects_unknown_values(api_client):
    client, jf_db = api_client
    career, _quest = _seed_pair(jf_db)
    resp = client.patch(
        f"/api/v1/applications/{career.id}/status", json={"status": "abducted"}
    )
    assert resp.status_code == 422
