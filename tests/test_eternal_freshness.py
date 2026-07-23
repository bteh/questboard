"""Eternal-freshness bug: relative prose dates anchored to NOW at query time.

A row scraped 6 days ago whose source said "Reposted 3 Days Ago" read as
3 days old forever, so posted_within_days=3 kept leaking it onto the board.
The fix anchors relative prose to the row's date_found (scrape time):
age = age(date_found) + stated offset. Prose with no anchor is unknown
(None), which an explicit freshness filter excludes.

Also pins the SQL predicate in application_service: prose and bare epoch
date_posted values must DROP under an explicit posted_within_days filter.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Piece 1: _source_age_days anchor semantics ──


def test_prose_age_is_anchored_to_scrape_time():
    from app.services.local_agent_service import _source_age_days

    anchor = _now() - timedelta(days=6)
    # Scraped 6 days ago, source said "3 days ago" then: ~9 days old NOW.
    assert 8.5 < _source_age_days("Reposted 3 Days Ago", anchor) < 9.5
    assert 8.5 < _source_age_days("3 days ago", anchor) < 9.5
    assert 6.5 < _source_age_days("Yesterday", anchor) < 7.5
    assert 5.9 < _source_age_days("Posted 20 Hours Ago", anchor) < 7.0
    assert 5.5 < _source_age_days("Posted Today", anchor) < 6.5
    # The anchor can arrive as the stored ISO string too.
    assert 8.5 < _source_age_days("Reposted 3 Days Ago", anchor.isoformat()) < 9.5
    # Naive datetimes (how SQLite hands date_found back) are UTC.
    naive = anchor.replace(tzinfo=None)
    assert 8.5 < _source_age_days("Reposted 3 Days Ago", naive) < 9.5


def test_prose_without_anchor_is_unknown():
    from app.services.local_agent_service import _source_age_days

    assert _source_age_days("Reposted 3 Days Ago") is None
    assert _source_age_days("3 days ago") is None
    assert _source_age_days("Posted Today") is None
    assert _source_age_days("Yesterday") is None
    assert _source_age_days("Posted 20 Hours Ago", None) is None


def test_absolute_dates_ignore_the_anchor():
    from app.services.local_agent_service import _source_age_days

    two_days_ago = _now() - timedelta(days=2)
    stale_anchor = _now() - timedelta(days=30)
    # ISO stays anchored to now, with or without an anchor argument.
    assert 1.5 < _source_age_days(two_days_ago.isoformat()) < 2.5
    assert 1.5 < _source_age_days(two_days_ago.isoformat(), stale_anchor) < 2.5
    # Epoch seconds and millis likewise.
    epoch = str(int(time.time()) - 2 * 86_400)
    assert 1.5 < _source_age_days(epoch) < 2.5
    assert 1.5 < _source_age_days(epoch, stale_anchor) < 2.5
    assert 1.5 < _source_age_days(epoch + "000", stale_anchor) < 2.5
    # Junk stays unknown either way.
    assert _source_age_days("not a date", stale_anchor) is None
    assert _source_age_days("", stale_anchor) is None


# ── Piece 2: the user's exact leak through search_work ──


@pytest.fixture()
def freshness_db(tmp_path, monkeypatch):
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
    now = _now()
    db.add(
        Workspace(
            id="local",
            name="Local",
            slug="local",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(["Data Engineering Manager"]),
            workplace_preference="remote_friendly",
            max_days_old=30,
        )
    )
    db.commit()
    yield db
    generator.close()


def test_stale_prose_row_leaves_a_3_day_window_but_stays_in_a_30_day_one(
    freshness_db,
) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    now = _now()
    freshness_db.add(
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company="Eternal Freshness Co",
            location="Remote, US",
            remote_scope="us",
            is_remote=True,
            job_url="https://stale-prose.example/jobs/data",
            source="BuiltIn",
            vertical="career",
            # The live leak: source said "3 Days Ago" when we scraped it,
            # 6.5 days ago. Real age is ~9.5 days.
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
            date_found=now - timedelta(days=6, hours=12),
        )
    )
    freshness_db.commit()

    tight = local_agent_service.search_work(
        freshness_db,
        queries=["Data Engineering Manager"],
        posted_within_days=3,
        page_size=20,
    )
    organizations = {row["organization"] for row in tight["results"]}
    assert "Eternal Freshness Co" not in organizations
    assert tight["freshness_filter_summary"]["known_stale_excluded"] == 1

    wide = local_agent_service.search_work(
        freshness_db,
        queries=["Data Engineering Manager"],
        posted_within_days=30,
        page_size=20,
    )
    wide_organizations = {row["organization"] for row in wide["results"]}
    assert "Eternal Freshness Co" in wide_organizations


# ── Piece 4: the SQL predicate drops prose and epoch under an explicit filter ──


def test_sql_posted_within_predicate_drops_prose_and_epoch(freshness_db) -> None:
    from app.services import application_service
    from job_finder.models.database import ApplicationRecord

    now = _now()
    freshness_db.add_all(
        [
            ApplicationRecord(
                job_title="Provable fresh row",
                company="ISO Co",
                job_url="https://iso.example/jobs/1",
                vertical="career",
                date_posted=(now - timedelta(days=2)).isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Prose yesterday row",
                company="Prose Co",
                job_url="https://prose.example/jobs/1",
                vertical="career",
                date_posted="Yesterday",
                date_confidence="fuzzy",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Bare epoch row",
                company="Epoch Co",
                job_url="https://epoch.example/jobs/1",
                vertical="career",
                # Even a genuinely fresh epoch cannot be proven by the string
                # predicate; it must drop, never guess in.
                date_posted=str(int(now.timestamp()) - 3600),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    freshness_db.commit()

    items, total = application_service.get_applications(
        freshness_db,
        posted_within_days=30,
        page_size=50,
        verticals=["career", "work"],
    )
    titles = {item.job_title for item in items}
    assert "Provable fresh row" in titles
    assert "Prose yesterday row" not in titles
    assert "Bare epoch row" not in titles
    assert total == 1


def test_ambiguous_epoch_length_is_unknown_not_fresh():
    """Only 10-digit (seconds) and 13-digit (ms) epochs are real; an 11 or
    12 digit value is malformed and must read as unknown, never age 0."""
    from app.services.local_agent_service import _source_age_days

    assert _source_age_days("100000000001") is None  # 12 digits
    assert _source_age_days("10000000000") is None    # 11 digits
    # the two valid widths still parse
    assert _source_age_days("1784660000") is not None   # 10, seconds
    assert _source_age_days("1784660000000") is not None  # 13, ms
