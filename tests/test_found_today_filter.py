"""The found-today window filters by OUR clock, not the source's claim.

"Posted today" reads date_posted, the source's often-missing statement, and
hides undated rows; the reader used it twice expecting "what arrived today"
and saw 7 of 116 rows, all skips. found_within_days reads date_found, which
the board stamps itself on every row, so today's arrivals always qualify.
"""

from __future__ import annotations

import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


def _passes(record_date_found, days=1, *, timezone_name="UTC", now=None):
    from app.services.application_service import board_filter_conditions
    from job_finder.models.database import ApplicationRecord
    from sqlalchemy import and_, create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    ApplicationRecord.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ApplicationRecord(
            job_title="t", company="c", job_url="https://x.example/1",
            vertical="career", date_found=record_date_found,
        ))
        db.commit()
        clock = (
            patch("app.services.application_service._utcnow", return_value=now)
            if now
            else nullcontext()
        )
        with clock:
            conds = board_filter_conditions(
                ApplicationRecord,
                found_within_days=days,
                timezone_name=timezone_name,
            )
        q = db.query(ApplicationRecord).filter(and_(*conds))
        return q.count() == 1
def test_a_row_found_after_local_midnight_passes():
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    assert _passes(
        datetime(2026, 8, 3, 7, 0),
        timezone_name="America/Los_Angeles",
        now=now,
    )


def test_a_row_from_the_previous_local_day_does_not_pass_even_within_24_hours():
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    assert not _passes(
        datetime(2026, 8, 3, 6, 59, 59),
        timezone_name="America/Los_Angeles",
        now=now,
    )


def test_a_future_timestamp_does_not_pass_today():
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    assert not _passes(
        datetime(2026, 8, 4, 7, 0),
        timezone_name="America/Los_Angeles",
        now=now,
    )


def test_a_later_timestamp_on_the_same_local_day_does_not_pass_today():
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    assert not _passes(
        datetime(2026, 8, 3, 16, 0),
        timezone_name="America/Los_Angeles",
        now=now,
    )


def test_calendar_bounds_follow_dst_instead_of_assuming_24_hours():
    from app.services.application_service import local_calendar_window_utc

    start, end = local_calendar_window_utc(
        1,
        "America/Los_Angeles",
        now=datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc),
    )
    assert start == datetime(2026, 3, 8, 8, 0)
    assert end == datetime(2026, 3, 9, 7, 0)


def test_no_window_means_no_condition():
    from app.services.application_service import board_filter_conditions
    from job_finder.models.database import ApplicationRecord

    with_f = board_filter_conditions(ApplicationRecord, found_within_days=1)
    without = board_filter_conditions(ApplicationRecord)
    # One shared condition owns the arrival window and stale-source guard.
    assert len(with_f) == len(without) + 1


def test_search_work_found_window_keeps_todays_row_and_drops_last_weeks(tmp_path, monkeypatch):
    """The My roles view goes through search_work, so the window must hold
    there too, not just in the generic board filters."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'db.db'}")
    from app.models.database import get_db, init_db

    init_db(str(data_dir / "db.db"))
    gen = get_db()
    db = next(gen)
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for title, found in [("Data Engineering Manager", today_start),
                         ("Data Engineering Manager II", now - timedelta(days=6)),
                         ("Data Engineering Manager Future", now + timedelta(hours=2))]:
        db.add(ApplicationRecord(
            job_title=title, company="c", job_url=f"https://x.example/{title}",
            vertical="career", date_found=found, description="d",
        ))
    db.commit()
    from app.services import local_agent_service as svc

    payload = svc.search_work(db, queries=["Data Engineering Manager"],
                              use_saved_preferences=False, found_within_days=1)
    titles = [c["title"] for c in payload["results"]]
    assert "Data Engineering Manager" in titles
    assert "Data Engineering Manager II" not in titles
    assert "Data Engineering Manager Future" not in titles
    db.close()


def _passes_with_posted(record_date_found, date_posted, days=1):
    from app.services.application_service import board_filter_conditions
    from job_finder.models.database import ApplicationRecord
    from sqlalchemy import and_, create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    ApplicationRecord.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ApplicationRecord(
            job_title="t", company="c", job_url="https://x.example/1",
            vertical="career", date_found=record_date_found, date_posted=date_posted,
        ))
        db.commit()
        conds = board_filter_conditions(ApplicationRecord, found_within_days=days)
        return db.query(ApplicationRecord).filter(and_(*conds)).count() == 1


def test_a_stale_posting_the_board_just_met_is_not_a_fresh_find():
    """Netflix EM, posted 19 days ago, crawled today: found-today showed it
    and the reader rightly objected. Found means fresh find: new to the board
    AND not provably weeks old at the source."""
    assert not _passes_with_posted(
        datetime.now(timezone.utc) - timedelta(hours=2),
        (datetime.now(timezone.utc) - timedelta(days=19)).strftime("%Y-%m-%dT00:00:00"),
    )


def test_an_undated_fresh_find_is_kept():
    """No posted date proves nothing; arrival is still the board's own fact."""
    now = datetime.now(timezone.utc)
    assert _passes_with_posted(
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        None,
    )


def test_a_new_source_date_does_not_resurrect_an_older_board_row():
    """New today is first-seen today; changing source metadata is not a new row."""
    assert not _passes_with_posted(
        datetime.now(timezone.utc) - timedelta(days=5),
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    )
