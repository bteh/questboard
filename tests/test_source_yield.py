"""A source's health and a source's worth to you are different questions.

The run log says whether a scraper worked. It cannot say whether the scraper
is worth its time to a particular person, because whether a found job survives
is entirely about that person's roles, place, and pay.

Measured on one real board, 2026-07-27:

    workday    found 266 jobs, 44.6s, 4 rows kept
    himalayas  found  59 jobs, 22.0s, 444 rows kept

Reading that as "drop Workday" would be wrong. Workday is the dominant ATS for
enterprise IT and healthcare, so for a different search it is the best source
on the board. The numbers belong next to each other, per person, and the
verdict stays with the person.
"""

from __future__ import annotations

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
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    db = next(get_db())
    now = datetime.now(timezone.utc)

    def row(source, **kw):
        return ApplicationRecord(
            job_title="Data Engineering Manager",
            company=f"Co {source}{kw.get('n', '')}",
            job_url=f"https://example.com/{source}/{kw.pop('n', 0)}",
            source=source,
            vertical=kw.pop("vertical", "career"),
            date_found=now - timedelta(minutes=1),
            last_seen_at=now,
            **kw,
        )

    db.add_all([
        row("Himalayas", n=1), row("Himalayas", n=2), row("Himalayas", n=3),
        row("Workday", n=4),
        row("Workday", n=5, url_status="dead"),       # off the board
        row("Workday", n=6, url_status="expired"),    # off the board
        row("Greenhouse", n=7),
        row("Respondent", n=8, vertical="think"),     # a quest, not work
    ])
    db.commit()
    yield db
    db.close()


def test_counts_only_what_is_still_on_the_board(board_db):
    from app.services.application_service import live_rows_by_source

    counts = live_rows_by_source(board_db)
    assert counts["himalayas"] == 3
    # found 3, but two are dead/expired tombstones the board hides
    assert counts["workday"] == 1
    assert counts["greenhouse"] == 1


def test_quest_rows_do_not_inflate_a_work_source(board_db):
    from app.services.application_service import live_rows_by_source

    assert "respondent" not in live_rows_by_source(board_db)


def test_keys_are_lowercase_so_they_join_the_run_log(board_db):
    """The run log writes 'workday'; the rows carry 'Workday'."""
    from app.services.application_service import live_rows_by_source

    counts = live_rows_by_source(board_db)
    assert all(key == key.lower() for key in counts)


def test_a_source_with_no_rows_is_absent_rather_than_zero(board_db):
    from app.services.application_service import live_rows_by_source

    counts = live_rows_by_source(board_db)
    assert "lever" not in counts
    assert counts.get("lever", 0) == 0  # the caller's default is what shows


def test_health_reports_what_the_latest_run_cost():
    """The slowest source sets the floor for the whole pull, since sources run
    concurrently. That cost belongs next to what the source delivered."""
    from job_finder.source_health import SourceHealth, verdict_for

    entry = SourceHealth(
        source="workday",
        vertical="career",
        verdict=verdict_for("ok", 266, 200),
        last_run_at=None,
        last_finish_reason="ok",
        last_rows=266,
        median_rows=200,
        runs_seen=3,
        error_sample="",
        last_seconds=44.6,
    )
    assert entry.last_seconds == 44.6
    # Finding plenty is still healthy, whatever it costs or whoever keeps it.
    assert entry.verdict == "ok"


def test_a_costly_low_yield_source_is_not_marked_unhealthy():
    """Fit is not health. A source can be slow and keep nothing for one person
    while working perfectly."""
    from job_finder.source_health import verdict_for

    assert verdict_for("ok", 266, 200) == "ok"
