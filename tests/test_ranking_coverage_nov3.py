"""Nov 3 2026 audit: "I've been seeing the same jobs".

Real board: 599 in-lane rows, 140 ranked, 343 waiting for review. The
connected agent's search_work swept only the newest 200 SQL candidates (45
rows after the gates), so the 343 older unreviewed rows never reached it and
sat below the ranked block forever. Separately, 8 cross-source duplicates the
auto-dedupe had tombstoned came back after the link checker re-stamped them
alive.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


def _make_db(tmp_path, monkeypatch, records):
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
            roles_json=json.dumps(["Data Engineering Manager"]),
            keywords_json=json.dumps([]),
            workplace_preference="remote_friendly",
            max_days_old=45,
        )
    )
    db.add_all(records)
    db.commit()
    return db, generator


def _record(i: int, *, title: str, found: datetime, posted: datetime, **extra):
    from job_finder.models.database import ApplicationRecord

    return ApplicationRecord(
        job_title=title,
        company=f"Co {i}",
        job_url=f"https://jobs.example/{i}",
        location="Los Angeles, CA",
        is_remote=False,
        source="greenhouse",
        vertical="career",
        date_posted=posted.date().isoformat(),
        date_confidence="exact",
        date_found=found,
        **extra,
    )


def test_agent_sweep_reaches_older_unreviewed_rows(tmp_path, monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # 260 newer arrivals that the freshness gate rejects fill the newest-200
    # SQL window; the 10 in-lane rows the agent never saw were found earlier.
    stale = [
        _record(i, title="Data Engineering Manager", found=now - timedelta(hours=i), posted=now - timedelta(days=120))
        for i in range(260)
    ]
    waiting = [
        _record(1000 + i, title="Data Engineering Manager", found=now - timedelta(days=12, hours=i), posted=now - timedelta(days=13))
        for i in range(10)
    ]
    db, generator = _make_db(tmp_path, monkeypatch, stale + waiting)
    try:
        from app.services import local_agent_service

        result = local_agent_service.search_work(db, page_size=20)
        assert result["needs_review_total"] == 10
        assert result["total_matching"] == 10
        returned = {row["opportunity_id"] for row in result["results"]}
        assert {rec.id for rec in waiting} <= returned
    finally:
        generator.close()


def test_board_hides_tombstoned_duplicate_even_if_link_reads_alive(tmp_path, monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    keeper = _record(1, title="Data Engineering Manager", found=now, posted=now, status="found", url_status="alive")
    tomb = _record(
        2,
        title="Manager, Data Engineering",
        found=now,
        posted=now,
        status="expired",
        url_status="alive",
        notes="Cross-source duplicate of #1 (greenhouse); collapsed after a search run.",
    )
    db, generator = _make_db(tmp_path, monkeypatch, [keeper, tomb])
    try:
        from app.services import local_agent_service

        result = local_agent_service.search_work(db, page_size=20, browse_all=True)
        ids = {row["opportunity_id"] for row in result["results"]}
        assert keeper.id in ids
        assert tomb.id not in ids
    finally:
        generator.close()


def test_link_check_leaves_tombstones_alone(tmp_path, monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tomb = _record(3, title="Data Engineering Manager", found=now, posted=now, status="expired", url_status="expired")
    db, generator = _make_db(tmp_path, monkeypatch, [tomb])

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("offline in tests")

    for name in ("get", "head", "request"):
        monkeypatch.setattr(requests, name, offline)
        monkeypatch.setattr(requests.Session, name, offline)
    try:
        from app.services import application_service

        application_service.check_urls(db, ids=[tomb.id])
        db.refresh(tomb)
        assert tomb.url_status == "expired"
    finally:
        generator.close()


def test_ladders_reposts_count_as_an_intermediary() -> None:
    """Ladders held 3 of the top 40 board spots with LinkedIn reposts that name no employer."""
    from job_finder.staffing import is_staffing_agency

    assert is_staffing_agency("Ladders")


def test_slug_company_with_brand_suffix_matches_display_name() -> None:
    """Lever slug "Gohighlevel" and Indeed "HighLevel" posted the same Sr. Engineering Manager role."""
    from job_finder.dedup import companies_match, company_key

    assert companies_match(company_key("Gohighlevel"), company_key("HighLevel"))
    assert not companies_match(company_key("Dropbox"), company_key("Box"))
    assert not companies_match(company_key("Unsnap"), company_key("Snap"))
