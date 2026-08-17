"""The level filter must never drop a title the user saved as a target role.

Real case: saved roles are "Staff Data Engineer", "Data Engineering Manager",
and "Director, Data Platform". A current_title resolving to director (6) with
balanced tol_senior=1.5 kept only level >= 4.5, silently dropping the Staff
and Manager titles the user asked for by name; a mid (2) current level kept
only <= 4.0 and dropped the Director title the same way. A saved role that
names a level is a stronger statement of intent than a band derived from
current_title, so a matching title at that role's level bypasses the cut.
Level-agnostic roles ("Data Scientist") don't widen the band — that keeps
the filter able to refine broad roles (pinned in
test_local_agent_review_fixes.py::test_strict_ranking_matches_pull_freshness_and_level_filters).
Both call sites (pipeline pre-store and local agent read time) inherit the
bypass from _filter_jobs_by_level.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.pipeline import _filter_jobs_by_level, _resolve_filter_settings  # noqa: E402

SAVED_ROLES = [
    "Staff Data Engineer",
    "Data Engineering Manager",
    "Director, Data Platform",
]


def _titles(jobs):
    return [j["title"] for j in jobs]


def test_director_current_title_keeps_staff_and_manager_saved_roles():
    jobs = [
        {"title": "Staff Data Engineer", "is_remote": True},
        {"title": "Data Engineering Manager", "is_remote": True},
        {"title": "Junior Sales Associate", "is_remote": True},
    ]
    kept = _filter_jobs_by_level(
        jobs,
        {"current_title": "Director, Data Platform"},
        filters=_resolve_filter_settings(None),
        target_roles=SAVED_ROLES,
    )
    assert _titles(kept) == ["Staff Data Engineer", "Data Engineering Manager"]


def test_mid_current_level_keeps_director_saved_role():
    jobs = [
        {"title": "Director, Data Platform", "is_remote": True},
        {"title": "SVP of Sales", "is_remote": True},
    ]
    kept = _filter_jobs_by_level(
        jobs,
        {"current_level": "mid"},
        filters=_resolve_filter_settings(None),
        target_roles=SAVED_ROLES,
    )
    assert _titles(kept) == ["Director, Data Platform"]


def test_level_agnostic_saved_role_still_gets_level_refinement():
    jobs = [{"title": "Junior Data Scientist", "is_remote": True}]
    kept = _filter_jobs_by_level(
        jobs,
        {"current_level": "manager"},
        filters=_resolve_filter_settings({"filters": {"strictness": "strict"}}),
        target_roles=["Data Scientist"],
    )
    assert kept == []


def test_level_filter_unchanged_without_saved_roles():
    jobs = [{"title": "Staff Data Engineer", "is_remote": True}]
    kept = _filter_jobs_by_level(
        jobs,
        {"current_title": "Director, Data Platform"},
        filters=_resolve_filter_settings(None),
    )
    assert kept == []


@pytest.fixture()
def read_time_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)

    db.add(
        Workspace(
            id="ws",
            name="Ws",
            slug="ws",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="ws",
            roles_json=json.dumps(SAVED_ROLES),
            preferred_places_json=json.dumps(
                [
                    {
                        "label": "Los Angeles, CA",
                        "kind": "city",
                        "match_scope": "city",
                        "city": "Los Angeles",
                        "region": "California",
                        "country": "United States",
                        "country_code": "us",
                    }
                ]
            ),
            workplace_preference="remote_friendly",
            max_days_old=14,
            current_level="director",
        )
    )
    db.add(
        WorkspaceResume(
            workspace_id="ws",
            original_filename="resume.pdf",
            parse_status="parsed",
            file_sha256="a" * 64,
            extracted_text="Data platform leadership resume.",
            updated_at=now,
        )
    )
    db.add(
        ApplicationRecord(
            job_title="Staff Data Engineer",
            company="Choke Point Co",
            location="Los Angeles, CA",
            state_codes=",CA,",
            remote_scope="us",
            job_url="https://example.com/jobs/staff-de",
            source="Greenhouse",
            description="Build the data platform.",
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
            last_seen_at=now,
        )
    )
    db.commit()
    yield db
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def test_read_time_search_keeps_saved_role_despite_director_level(read_time_db):
    from app.services import local_agent_service

    payload = local_agent_service.search_work(
        read_time_db,
        queries=["Staff Data Engineer"],
        page_size=20,
    )
    assert "Choke Point Co" in {row["organization"] for row in payload["results"]}
