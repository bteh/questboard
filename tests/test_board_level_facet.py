"""The Find work board can be narrowed by level, with honest counts.

Real case (Sep 17 2026): the board held 61 lead-level and 211 manager-level
postings, sorted newest first, 24 per page. The person read the first
pages, saw managers and directors, and concluded there were no lead roles.
A level chip row (Lead, Manager, Director...) with counts makes the split
visible and lets them narrow to it, the way the source chips already do.

Rules under test:
1. The profile-work response carries ``levels``: a count per leadership
   level over the visible lane (so it reflects the level bounding), and a
   title's level is its leadership word (senior manager = manager, head =
   director, team lead = lead).
2. ``level=lead`` narrows the items to that level; the counts stay those of
   the whole lane so every chip shows what clicking it yields.
3. An unknown level is a 400.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

TITLES = [
    "Data Engineering Manager",
    "Senior Manager, Data Engineering",
    "Manager, Data Platform",
    "Lead Data Engineer",
    "Data Engineering Team Lead",
    "Director of Data Engineering",
    "Head of Data",
    "Senior Data Engineer",
]


@pytest.fixture()
def board_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(Workspace(id="local", name="Local", slug="local", last_active_at=now, expires_at=now + timedelta(days=7)))
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(["Data Engineering Manager", "Data Engineering Lead"]),
            keywords_json=json.dumps([]),
            workplace_preference="remote_friendly",
            max_days_old=45,
        )
    )
    db.add_all(
        [
            ApplicationRecord(
                job_title=title,
                company=f"Co {i}",
                job_url=f"https://jobs.example/{i}",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                is_remote=False,
                source="greenhouse",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            )
            for i, title in enumerate(TITLES)
        ]
    )
    db.commit()
    yield db
    generator.close()


def _call(db, **overrides):
    from app.api.applications import list_profile_work

    kwargs = dict(
        search=None,
        location=None,
        location_strict=False,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        is_remote=None,
        founding_only=False,
        posted_within_days=None,
        found_within_days=None,
        timezone_name="UTC",
        source_category=None,
        level=None,
        sort_by="date_found",
        page=1,
        page_size=24,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="local")),
        db=db,
    )
    kwargs.update(overrides)
    return list_profile_work(**kwargs)


def test_levels_count_the_visible_lane_per_leadership_level(board_db) -> None:
    response = _call(board_db)
    titles = {item.job_title for item in response.items}
    assert {"Data Engineering Manager", "Senior Manager, Data Engineering", "Manager, Data Platform", "Lead Data Engineer", "Data Engineering Team Lead"} <= titles
    assert response.levels == {"lead": 2, "manager": 3}


def test_level_narrows_the_items_and_keeps_lane_counts(board_db) -> None:
    response = _call(board_db, level="lead")
    assert {item.job_title for item in response.items} == {"Lead Data Engineer", "Data Engineering Team Lead"}
    assert response.total == 2
    assert response.levels == {"lead": 2, "manager": 3}


def test_unknown_level_is_rejected(board_db) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _call(board_db, level="boss")
    assert excinfo.value.status_code == 400


def test_title_level_vocabulary() -> None:
    from app.services import local_agent_service as las

    assert las.title_level("Senior Manager, Data Engineering") == "manager"
    assert las.title_level("Engineering Mgr, Data") == "manager"
    assert las.title_level("Data Engineering Team Lead") == "lead"
    assert las.title_level("Tech Lead, Data Platform") == "lead"
    assert las.title_level("Head of Data") == "director"
    assert las.title_level("Associate Director, Analytics") == "director"
    assert las.title_level("VP, Data Engineering") == "vp"
    assert las.title_level("Senior Vice President, Data") == "vp"
    assert las.title_level("Chief Data Officer") == "chief"
    assert las.title_level("Senior Data Engineer") is None
    assert las.title_level("Leadership Development Analyst") is None
