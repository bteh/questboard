"""A leadership seeker's board shows the whole data-leadership family.

Real case (Sep 15 2026): saved roles were ten data leadership titles
(Data Engineering Manager, Head of Data Platform, Director of Data
Engineering, ...). The pull had 1,451 fresh, pay-OK, in-place rows and 458
of them carried a leadership word plus a data word in the title, yet the
board showed 86. The board's SQL prefilter required every token of one
saved role in the title, so "Head of Data", "Director, Data Platform",
"VP, Data Engineering" and "Data Analytics Manager" never reached the
Python lane and role gates that would have kept them.

Rules under test:
1. When the saved roles carry a leadership word, the prefilter retrieves
   any title that shares a domain word with a role AND carries a leadership
   word; the Python gates then decide. Individual-contributor titles stay
   hidden for a leadership seeker.
2. A seeker with individual-contributor roles keeps today's behaviour: the
   role's own words must all be in the title.
3. The SQL layer expands the level words it is sent: manager also matches
   mgr, vp matches vice president and vice-president, chief matches CTO,
   CDO and CIO.
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
    db.commit()
    return db, generator


def _seed(db, titles: list[tuple[str, bool]]) -> None:
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            ApplicationRecord(
                job_title=title,
                company=f"Co {i}",
                job_url=f"https://jobs.example/{i}",
                location="Remote, US" if remote else "Los Angeles, CA",
                is_remote=remote,
                source="greenhouse",
                vertical="career",
                date_posted="",
                date_found=now,
            )
            for i, (title, remote) in enumerate(titles)
        ]
    )
    db.commit()


def _visible_titles(db) -> set[str]:
    from app.services import local_agent_service

    # The shortlist call returns full rows; browse_all returns ids only.
    result = local_agent_service.search_work(db, page_size=50)
    return {str(row["title"]) for row in result["results"]}


@pytest.fixture()
def leadership_db(tmp_path, monkeypatch):
    db, generator = _make_db(tmp_path, monkeypatch, ["Data Engineering Manager", "Head of Data Platform"])
    _seed(
        db,
        [
            ("Data Engineering Manager", False),
            ("Head of Data", False),
            ("Director, Data Platform", False),
            ("VP, Data Engineering", True),
            ("Data Analytics Manager", False),
            ("Senior Data Engineer", False),
            ("Data Engineer", True),
            ("Engineering Manager, Applied AI", True),
            ("Product Manager, Data", False),
        ],
    )
    yield db
    generator.close()


@pytest.fixture()
def ic_db(tmp_path, monkeypatch):
    db, generator = _make_db(tmp_path, monkeypatch, ["Data Engineer"])
    _seed(
        db,
        [
            ("Senior Data Engineer", True),
            ("Data Engineer", False),
            ("Head of Data", False),
            ("Data Analyst", False),
        ],
    )
    yield db
    generator.close()


def test_leadership_seeker_sees_the_whole_data_leadership_family(leadership_db) -> None:
    visible = _visible_titles(leadership_db)
    assert {
        "Data Engineering Manager",
        "Head of Data",
        "Director, Data Platform",
        "Data Analytics Manager",
    } <= visible
    # Sep 17 2026: the family is bounded by the saved levels (manager and
    # head-of here), so VP stays out unless a saved role names it.
    assert "VP, Data Engineering" not in visible


def test_leadership_seeker_does_not_see_individual_contributor_titles(leadership_db) -> None:
    visible = _visible_titles(leadership_db)
    assert "Senior Data Engineer" not in visible
    assert "Data Engineer" not in visible
    assert "Engineering Manager, Applied AI" not in visible
    assert "Product Manager, Data" not in visible


def test_individual_contributor_seeker_keeps_todays_matching(ic_db) -> None:
    visible = _visible_titles(ic_db)
    assert {"Senior Data Engineer", "Data Engineer"} <= visible
    assert "Head of Data" not in visible
    assert "Data Analyst" not in visible


def test_sql_chief_token_expands_to_its_acronyms(tmp_path, monkeypatch) -> None:
    """A chief seeker's [data, chief] group answers "CDO, Data" and "CTO, Data
    Platform" as well as "Chief Data Officer", and not the directors whose
    word happens to contain "cto"."""
    from app.services import application_service

    db, generator = _make_db(tmp_path, monkeypatch, ["Chief Data Officer"])
    try:
        _seed(
            db,
            [
                ("Chief Data Officer", False),
                ("CDO, Data", False),
                ("CTO, Data Platform", False),
                ("Director of Data", False),
                ("Senior Data Engineer", False),
            ],
        )
        rows, total = application_service.get_applications(
            db, title_token_groups=[["data", "chief"]], page_size=50
        )
        titles = {row.job_title for row in rows}
        assert total == 3
        assert titles == {"Chief Data Officer", "CDO, Data", "CTO, Data Platform"}
    finally:
        generator.close()
