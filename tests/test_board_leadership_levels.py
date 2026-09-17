"""The leadership family is bounded by the levels the person saved.

Real case (Sep 17 2026): saved roles were manager and lead titles (plus a
director and a head-of role the assistant had proposed as a stretch). The
board showed 94 director, 17 head-of and 5 VP postings next to 211 manager
and 61 lead ones, because the 0.2.9 family rule expanded to every
leadership word. The person is a manager and said director is not the
level yet. "Titles you want next" means the levels you saved, no higher.

Rules under test:
1. A seeker with manager and lead roles sees manager, senior manager and
   lead titles, and never director, head-of, VP or chief titles, nor
   individual-contributor titles.
2. Saving a director role admits director and head-of titles (one family),
   VP and chief stay out unless saved.
3. An individual-contributor seeker is unchanged.
4. The SQL retrieval groups pair each domain word with each saved level
   word, not with a catch-all leadership token.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    "Tech Lead, Data Platform",
    "Director of Data Engineering",
    "Director, Data Platform",
    "Head of Data",
    "VP, Data Engineering",
    "Chief Data Officer",
    "Senior Data Engineer",
    "Staff Data Engineer",
]


def _make_db(tmp_path, monkeypatch, roles: list[str]):
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
            roles_json=json.dumps(roles),
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
                is_remote=False,
                source="greenhouse",
                vertical="career",
                date_posted="",
                date_found=now,
            )
            for i, title in enumerate(TITLES)
        ]
    )
    db.commit()
    return db, generator


def _visible(db) -> set[str]:
    from app.services import local_agent_service

    result = local_agent_service.search_work(db, page_size=50)
    return {str(row["title"]) for row in result["results"]}


def test_manager_and_lead_seeker_sees_only_those_levels(tmp_path, monkeypatch) -> None:
    db, generator = _make_db(tmp_path, monkeypatch, ["Data Engineering Manager", "Data Engineering Lead"])
    try:
        visible = _visible(db)
        assert {
            "Data Engineering Manager",
            "Senior Manager, Data Engineering",
            "Manager, Data Platform",
            "Lead Data Engineer",
            "Tech Lead, Data Platform",
        } <= visible
        for hidden in (
            "Director of Data Engineering",
            "Director, Data Platform",
            "Head of Data",
            "VP, Data Engineering",
            "Chief Data Officer",
            "Senior Data Engineer",
            "Staff Data Engineer",
        ):
            assert hidden not in visible, hidden
    finally:
        generator.close()


def test_saving_a_director_role_admits_director_and_head_of_titles(tmp_path, monkeypatch) -> None:
    db, generator = _make_db(tmp_path, monkeypatch, ["Data Engineering Manager", "Director of Data Engineering"])
    try:
        visible = _visible(db)
        assert {"Data Engineering Manager", "Director of Data Engineering", "Director, Data Platform", "Head of Data"} <= visible
        assert "VP, Data Engineering" not in visible
        assert "Chief Data Officer" not in visible
        assert "Lead Data Engineer" not in visible
    finally:
        generator.close()


def test_individual_contributor_seeker_is_unchanged(tmp_path, monkeypatch) -> None:
    db, generator = _make_db(tmp_path, monkeypatch, ["Data Engineer"])
    try:
        visible = _visible(db)
        assert {"Senior Data Engineer", "Staff Data Engineer"} <= visible
        assert "Director of Data Engineering" not in visible
        assert "VP, Data Engineering" not in visible
    finally:
        generator.close()


def test_retrieval_groups_pair_domain_words_with_saved_levels_only() -> None:
    from app.services import local_agent_service as las

    groups = las._retrieval_token_groups(["Data Engineering Manager", "Data Engineering Lead"])
    as_sets = {frozenset(group) for group in groups}
    assert as_sets == {
        frozenset({"data", "manager"}),
        frozenset({"data", "lead"}),
        frozenset({"engineer", "manager"}),
        frozenset({"engineer", "lead"}),
    }
    assert not any("leadership" in group for group in groups)
    assert not any("director" in group or "vp" in group for group in groups)
