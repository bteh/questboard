"""Healthy-run-gated expiry: listings leave the board only with evidence.

Pins the trust contract from docs/source-reliability.md: absence expiry
needs two healthy runs of history (a broken scraper can never empty the
board), windowed sources expire by their declared staleness TTL, the
mass-expiry guard refuses suspicious wipeouts, tombstoned rows revive
when the source re-lists them, and confirmation never reshuffles the
user's log (updated_at stays put).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
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


@pytest.fixture()
def db(tmp_path):
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(tmp_path / "expiry.db"))
    yield jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


@pytest.fixture()
def fake_sources():
    """One full-snapshot source and one windowed (TTL) source."""
    import importlib

    # the scrapers package shadows `_registry` with the dict; go via importlib
    reg = importlib.import_module("job_finder.tools.scrapers._registry")

    @reg.register_scraper(
        name="_snap_src", display_name="Snap", url="https://s.example",
        kind="house", full_snapshot=True, enabled_by_default=False,
    )
    def _snap(**_kwargs):
        return []

    @reg.register_scraper(
        name="_ttl_src", display_name="Ttl", url="https://t.example",
        kind="odd", stale_after_days=2, enabled_by_default=False,
    )
    def _ttl(**_kwargs):
        return []

    yield "_snap_src", "_ttl_src"
    reg._REGISTRY.pop("_snap_src", None)
    reg._REGISTRY.pop("_ttl_src", None)


def _seed_row(db, source: str, url: str, *, seen_days_ago: float | None, vertical: str = "house"):
    record = db.save_application(
        job_title=f"Row {url[-6:]}",
        company="Fixture",
        job_url=url,
        source=source,
        vertical=vertical,
    )
    if seen_days_ago is not None:
        session = db.get_session()
        try:
            row = session.get(db.ApplicationRecord, record.id)
            row.last_seen_at = datetime.utcnow() - timedelta(days=seen_days_ago)
            session.commit()
        finally:
            session.close()
    return record.id


def _record_healthy_runs(db, source: str, *started_days_ago: float) -> None:
    db.record_scrape_runs([
        {
            "source": source,
            "rows_found": 20,
            "finish_reason": "ok",
            "started_at": datetime.utcnow() - timedelta(days=days),
        }
        for days in started_days_ago
    ])


def _status(db, row_id: int) -> str:
    session = db.get_session()
    try:
        return session.get(db.ApplicationRecord, row_id).url_status
    finally:
        session.close()


def test_absence_expiry_needs_two_healthy_runs(db, fake_sources):
    from job_finder.expiry import expire_for_source

    snap, _ = fake_sources
    stale = _seed_row(db, snap, "https://s.example/gone", seen_days_ago=5)

    _record_healthy_runs(db, snap, 0.1)  # one healthy run is not evidence
    result = expire_for_source(snap)
    assert result["expired"] == 0
    assert "two healthy runs" in result["skipped"]
    assert _status(db, stale) == "unknown"

    _record_healthy_runs(db, snap, 1)  # now two healthy runs of history
    result = expire_for_source(snap)
    assert result["rule"] == "absence"
    assert result["expired"] == 1
    assert _status(db, stale) == "expired"


def test_absence_spares_rows_the_latest_healthy_run_confirmed(db, fake_sources):
    from job_finder.expiry import expire_for_source

    snap, _ = fake_sources
    fresh = _seed_row(db, snap, "https://s.example/fresh", seen_days_ago=None)
    _record_healthy_runs(db, snap, 2, 0.1)

    assert expire_for_source(snap)["expired"] == 0
    assert _status(db, fresh) == "unknown"


def test_absence_expiry_refuses_a_failed_latest_run(db, fake_sources):
    """Old healthy history cannot make a timeout look like absence evidence."""
    from job_finder.expiry import expire_for_source

    snap, _ = fake_sources
    stale = _seed_row(db, snap, "https://s.example/still-live", seen_days_ago=5)
    _record_healthy_runs(db, snap, 2, 1)
    db.record_scrape_runs([{
        "source": snap,
        "rows_found": 0,
        "finish_reason": "timeout",
        "started_at": datetime.utcnow(),
    }])

    result = expire_for_source(snap)
    assert result["expired"] == 0
    assert "latest run incomplete: timeout" in result["skipped"]
    assert _status(db, stale) == "unknown"


def test_staleness_ttl_expires_unconfirmed_rows(db, fake_sources):
    from job_finder.expiry import expire_for_source

    _, ttl = fake_sources
    old = _seed_row(db, ttl, "https://t.example/old", seen_days_ago=3, vertical="odd")
    fresh = _seed_row(db, ttl, "https://t.example/new", seen_days_ago=None, vertical="odd")

    result = expire_for_source(ttl)
    assert result["rule"] == "stale"
    assert result["expired"] == 1
    assert _status(db, old) == "expired"
    assert _status(db, fresh) == "unknown"


def test_mass_expiry_guard_refuses_suspicious_wipeouts(db, fake_sources):
    from job_finder.expiry import expire_for_source

    _, ttl = fake_sources
    ids = [
        _seed_row(db, ttl, f"https://t.example/{i}", seen_days_ago=3, vertical="odd")
        for i in range(12)
    ]

    result = expire_for_source(ttl)
    assert result["expired"] == 0
    assert "mass-expiry guard" in result["skipped"]
    assert all(_status(db, i) == "unknown" for i in ids)


def test_null_last_seen_never_expires(db, fake_sources):
    from job_finder.expiry import expire_for_source

    _, ttl = fake_sources
    row = _seed_row(db, ttl, "https://t.example/null", seen_days_ago=None, vertical="odd")
    session = db.get_session()
    try:
        session.get(db.ApplicationRecord, row).last_seen_at = None
        session.commit()
    finally:
        session.close()

    assert expire_for_source(ttl)["expired"] == 0
    assert _status(db, row) == "unknown"


def test_undeclared_and_career_sources_are_no_ops(db):
    from job_finder.expiry import expire_for_source

    assert expire_for_source("remotive")["rule"] == "none"  # career source
    assert expire_for_source("nonexistent-source")["rule"] == "none"


def test_quest_refresh_never_truncates_a_full_snapshot(db, fake_sources, monkeypatch):
    """The absence rule is only sound when full_snapshot sources fetch their
    ENTIRE current set; a truncating cap would expire live offers."""
    import job_finder.quests as quests

    snap, _ = fake_sources
    seen: dict = {}

    def fake_run(names=None, max_results=0, **_kwargs):
        seen["max_results"] = max_results
        seen["max_results_by_source"] = _kwargs.get("max_results_by_source", {})
        return []

    monkeypatch.setattr(quests, "run_scrapers", fake_run)
    quests.run_quest_search(["house"])
    assert seen["max_results"] >= 100
    assert seen["max_results_by_source"][snap] >= 500


def test_resave_revives_a_tombstone_and_keeps_the_log_order(db, fake_sources):
    _, ttl = fake_sources
    row_id = _seed_row(db, ttl, "https://t.example/back", seen_days_ago=3, vertical="odd")
    session = db.get_session()
    try:
        row = session.get(db.ApplicationRecord, row_id)
        row.url_status = "expired"
        session.commit()
        before_updated = row.updated_at
    finally:
        session.close()

    revived = db.save_application(
        job_title="Row back",
        company="Fixture",
        job_url="https://t.example/back",
        source=ttl,
        vertical="odd",
    )
    assert revived.id == row_id
    assert revived.url_status == "unknown"
    assert revived.last_seen_at is not None
    # confirmation never reshuffles the user's log
    assert revived.updated_at == before_updated
