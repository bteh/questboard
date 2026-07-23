"""Layer 2: evidence-first discovery from the user's own application rows.

If the board already fed us a job whose URL carries a board token for
this company, that token is proven. It must win before any slug guessing
runs. Company matching goes through the cross-source normalizer in
job_finder.dedup, so "Bill.com Inc." on a stored row matches an added
"BILL". All tests seed a throwaway sqlite DB under JOB_FINDER_DATA_DIR
(per-test tmp dir via conftest); the live board is never touched.
"""

from __future__ import annotations

import os
import sqlite3

from app.services import watchlist_service


def _seed_applications(rows: list[tuple[str, str]]) -> str:
    """Create a minimal applications table in the per-test data dir."""
    data_dir = os.environ["JOB_FINDER_DATA_DIR"]
    db_path = os.path.join(data_dir, "job_tracker.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS applications ("
            "id INTEGER PRIMARY KEY, company TEXT, job_url TEXT)"
        )
        conn.executemany(
            "INSERT INTO applications (company, job_url) VALUES (?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _forbid_slug_guessing(monkeypatch):
    def boom(name):
        raise AssertionError("slug guessing must not run when evidence exists")

    monkeypatch.setattr(watchlist_service, "_generate_slugs", boom)


def test_evidence_row_wins_before_slug_guessing(monkeypatch):
    _seed_applications(
        [("Bill.com Inc.", "https://job-boards.greenhouse.io/billcom/jobs/771")]
    )
    _forbid_slug_guessing(monkeypatch)

    probed: list[str] = []

    def fake_probe(slug):
        probed.append(slug)
        return {
            "ats": "greenhouse",
            "slug": slug,
            "job_count": 7,
            "careers_url": f"https://boards.greenhouse.io/{slug}",
        }

    monkeypatch.setattr(watchlist_service, "_try_greenhouse", fake_probe)

    result = watchlist_service.discover_company("BILL")

    assert probed == ["billcom"]
    assert result == {
        "name": "BILL",
        "ats": "greenhouse",
        "slug": "billcom",
        "job_count": 7,
        "careers_url": "https://boards.greenhouse.io/billcom",
    }


def test_evidence_token_survives_a_failed_probe(monkeypatch):
    """The row already proved the token; a probe hiccup must not lose it."""
    _seed_applications(
        [("Umbra", "https://jobs.lever.co/umbra-hq/9f81-4a2b")]
    )
    _forbid_slug_guessing(monkeypatch)
    monkeypatch.setattr(watchlist_service, "_try_lever", lambda slug: None)

    result = watchlist_service.discover_company("Umbra")

    assert result["ats"] == "lever"
    assert result["slug"] == "umbra-hq"
    assert result["job_count"] == 0
    assert result["careers_url"] == "https://jobs.lever.co/umbra-hq"


def test_unrelated_companies_are_not_evidence(monkeypatch):
    _seed_applications(
        [("Stripe", "https://jobs.lever.co/stripe/9f81-4a2b")]
    )
    monkeypatch.setattr(watchlist_service, "_generate_slugs", lambda name: [])

    result = watchlist_service.discover_company("Figma")

    assert result["ats"] == "unknown"


def test_rows_without_a_board_token_are_skipped(monkeypatch):
    """A gh_jid company page names no board; it cannot serve as evidence."""
    _seed_applications(
        [("Umbra", "https://umbra.com/careers/opening?gh_jid=4021&src=greenhouse.io")]
    )
    monkeypatch.setattr(watchlist_service, "_generate_slugs", lambda name: [])

    result = watchlist_service.discover_company("Umbra")

    assert result["ats"] == "unknown"


def test_missing_db_falls_back_to_slug_guessing(monkeypatch):
    calls: list[str] = []

    def tracked(name):
        calls.append(name)
        return []

    monkeypatch.setattr(watchlist_service, "_generate_slugs", tracked)

    result = watchlist_service.discover_company("Figma")

    assert calls == ["Figma"]
    assert result["ats"] == "unknown"
