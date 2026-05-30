"""Stale postings should be dropped by their real post date.

max_days_old was only an upstream hint most boards ignore, and there was no
post-search age filter — so months-old repostings slipped through. This adds a
deterministic age gate that drops jobs older than max_days_old while KEEPING
jobs whose date is missing/unparseable (same philosophy as the salary filter).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.pipeline import _filter_jobs_by_freshness
from job_finder.tools.scrapers._utils import _parse_posted_date

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


def test_parse_iso():
    assert _parse_posted_date("2026-05-20").date() == datetime(2026, 5, 20).date()
    assert _parse_posted_date("2026-05-20T08:30:00Z").year == 2026


def test_parse_epoch_seconds():
    epoch = int(datetime(2026, 5, 20, tzinfo=timezone.utc).timestamp())
    assert _parse_posted_date(str(epoch)).date() == datetime(2026, 5, 20).date()
    assert _parse_posted_date(epoch).year == 2026


def test_parse_garbage_returns_none():
    assert _parse_posted_date("") is None
    assert _parse_posted_date("recently") is None
    assert _parse_posted_date(None) is None


def _job(date_posted):
    return {"title": "Engineer", "url": "u", "date_posted": date_posted}


def test_old_posting_dropped():
    old = (NOW - timedelta(days=45)).strftime("%Y-%m-%d")
    out = _filter_jobs_by_freshness([_job(old)], max_days_old=30, now=NOW)
    assert out == []


def test_recent_posting_kept():
    recent = (NOW - timedelta(days=5)).strftime("%Y-%m-%d")
    out = _filter_jobs_by_freshness([_job(recent)], max_days_old=30, now=NOW)
    assert len(out) == 1


def test_unknown_date_kept():
    assert len(_filter_jobs_by_freshness([_job("")], max_days_old=30, now=NOW)) == 1
    assert len(_filter_jobs_by_freshness([_job("whenever")], max_days_old=30, now=NOW)) == 1


def test_boundary_buffer_keeps_borderline():
    # Exactly at the cutoff (with the small skew buffer) is kept, not dropped.
    edge = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")
    assert len(_filter_jobs_by_freshness([_job(edge)], max_days_old=30, now=NOW)) == 1


def test_zero_max_days_disables_filter():
    old = (NOW - timedelta(days=365)).strftime("%Y-%m-%d")
    assert len(_filter_jobs_by_freshness([_job(old)], max_days_old=0, now=NOW)) == 1
