"""An older posting the source still shows as open stays on the board.

Real cases (Brian, Oct 1 2026), all hidden by the 45-day posted window alone:

- Natera "Sr. Software Engineer/Tech Lead, Data & AI Engineering", US remote,
  Greenhouse first_published Apr 6, updated_at Sep 29.
- Airbnb "Lead, Advanced Analytics, Payments", posted May 29, updated Sep 29.
- Stripe "Engineering Manager, Data Transformation", posted Apr 13, updated
  Sep 30.

On Sep 21, 145 verified-open lead and manager data postings were hidden from
the board by the window alone.

Rule under test: a posting is fresh if ANY of these holds, in this order of
evidence: ``posted`` (source post date within the window), ``updated`` (the
source says it was edited within the window), ``listed`` (the board still
listed it on a pull within the window, applications.last_seen_at),
``verified_open`` (the link check said alive within the window). A row kept by
anything other than ``posted`` carries the basis so the card can say "older,
still open". Rows with no evidence keep today's behaviour: an unknown date is
kept (basis None), an old date is dropped.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
WINDOW = 45
STORED = "%Y-%m-%dT%H:%M:%S"

NATERA_TITLE = "Sr. Software Engineer/Tech Lead, Data & AI Engineering"
NATERA_URL = "https://boards.greenhouse.io/natera/jobs/1"
AIRBNB_TITLE = "Lead, Advanced Analytics, Payments"
STRIPE_TITLE = "Engineering Manager, Data Transformation"


def _days_ago(days: int, *, now: datetime = NOW) -> datetime:
    return now - timedelta(days=days)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(STORED)


# ── Pull: _filter_jobs_by_freshness ──────────────────────────────────────────


def _job(posted_days_ago: int | None, **extra: object) -> dict:
    job: dict = {
        "title": AIRBNB_TITLE,
        "company": "Airbnb",
        "url": "https://careers.airbnb.com/positions/1",
        "date_posted": _iso(_days_ago(posted_days_ago)) if posted_days_ago is not None else "",
    }
    job.update(extra)
    return job


def test_pull_keeps_an_old_posting_the_source_updated_inside_the_window() -> None:
    from job_finder.pipeline import _filter_jobs_by_freshness

    job = _job(120, date_updated=_iso(_days_ago(3)))
    assert _filter_jobs_by_freshness([job], WINDOW, now=NOW) == [job]


def test_pull_keeps_an_old_posting_the_board_already_knows_by_url() -> None:
    from job_finder.pipeline import _filter_jobs_by_freshness

    job = _job(120)
    kept = _filter_jobs_by_freshness([job], WINDOW, now=NOW, known_urls={job["url"]})
    assert kept == [job]


def test_pull_drops_an_old_posting_with_no_evidence() -> None:
    from job_finder.pipeline import _filter_jobs_by_freshness

    assert _filter_jobs_by_freshness([_job(120)], WINDOW, now=NOW) == []
    assert (
        _filter_jobs_by_freshness(
            [_job(120)], WINDOW, now=NOW, known_urls={"https://other.example/1"}
        )
        == []
    )
    # An edit older than the window proves nothing.
    stale_edit = _job(120, date_updated=_iso(_days_ago(60)))
    assert _filter_jobs_by_freshness([stale_edit], WINDOW, now=NOW) == []


def test_pull_keeps_unknown_date_jobs_as_before() -> None:
    from job_finder.pipeline import _filter_jobs_by_freshness

    unknown = _job(None)
    assert _filter_jobs_by_freshness([unknown], WINDOW, now=NOW) == [unknown]
    assert _filter_jobs_by_freshness([unknown], WINDOW, now=NOW, known_urls=set()) == [unknown]


# ── Scraper: Greenhouse carries updated_at ───────────────────────────────────


def test_greenhouse_rows_carry_the_source_updated_date_in_the_calendar_shape() -> None:
    from job_finder.tools.scrapers import greenhouse

    board = {
        "jobs": [
            {
                "title": NATERA_TITLE,
                "location": {"name": "US Remote"},
                "absolute_url": NATERA_URL,
                "content": "<p>Own the data and AI platform.</p>",
                "first_published": "2026-04-06T10:00:00-04:00",
                "updated_at": "2026-09-29T15:07:18-04:00",
            }
        ]
    }
    with patch.object(greenhouse, "_get_json", return_value=board):
        jobs = greenhouse._fetch_company_jobs("natera", ["Software Engineer"])

    assert len(jobs) == 1
    assert jobs[0]["date_updated"] == "2026-09-29T19:07:18"
    assert jobs[0]["date_posted"].startswith("2026-04-06")


def test_greenhouse_without_updated_at_leaves_date_updated_empty() -> None:
    from job_finder.tools.scrapers import greenhouse

    board = {
        "jobs": [
            {
                "title": NATERA_TITLE,
                "location": {"name": "US Remote"},
                "absolute_url": NATERA_URL,
                "first_published": "2026-04-06T10:00:00-04:00",
            }
        ]
    }
    with patch.object(greenhouse, "_get_json", return_value=board):
        jobs = greenhouse._fetch_company_jobs("natera", ["Software Engineer"])

    assert jobs[0]["date_updated"] == ""


# ── Storage: applications.date_updated ───────────────────────────────────────


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("JOB_FINDER_MANAGE_SCHEMA", raising=False)
    from job_finder.models import database

    database.init_db(str(tmp_path / "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def _save_airbnb(store, **fields):
    base = dict(
        job_title=AIRBNB_TITLE,
        company="Airbnb",
        job_url="https://careers.airbnb.com/positions/1",
        source="greenhouse",
        date_posted="2026-05-29T10:00:00Z",
        date_confidence="exact",
    )
    base.update(fields)
    return store.save_application(**base)


def test_store_keeps_the_newest_source_updated_date_and_confirms_the_row(store) -> None:
    first = _save_airbnb(store, date_updated="2026-09-20T15:07:18-04:00")
    assert first.date_updated == "2026-09-20T19:07:18"
    first_seen = first.last_seen_at

    newer = _save_airbnb(store, date_updated="2026-09-29T15:07:18-04:00")
    assert newer.id == first.id
    assert newer.date_updated == "2026-09-29T19:07:18"
    assert newer.last_seen_at >= first_seen

    older = _save_airbnb(store, date_updated="2026-09-01T00:00:00Z")
    assert older.date_updated == "2026-09-29T19:07:18"

    blank = _save_airbnb(store)
    assert blank.date_updated == "2026-09-29T19:07:18"


def test_store_reports_which_urls_it_already_knows(store) -> None:
    _save_airbnb(store)
    known = store.known_job_urls(
        ["https://careers.airbnb.com/positions/1", "https://stripe.com/jobs/2", ""],
        profile="default",
        workspace_id=None,
    )
    assert known == {"https://careers.airbnb.com/positions/1"}
    assert store.known_job_urls([], profile="default", workspace_id=None) == set()
    # Another workspace's rows are not this workspace's evidence.
    assert (
        store.known_job_urls(
            ["https://careers.airbnb.com/positions/1"], profile="default", workspace_id="other"
        )
        == set()
    )


def test_migration_adds_date_updated_to_an_existing_table(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JOB_FINDER_MANAGE_SCHEMA", raising=False)
    from job_finder.models import database

    db_path = tmp_path / "job_tracker.db"
    database.init_db(str(db_path))
    database._SessionLocal.remove()
    database._engine.dispose()
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE applications DROP COLUMN date_updated")
        cols = [row[1] for row in conn.execute("PRAGMA table_info(applications)")]
        assert "date_updated" not in cols

    database.init_db(str(db_path))
    try:
        with sqlite3.connect(db_path) as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(applications)")]
        assert "date_updated" in cols
    finally:
        database._SessionLocal.remove()


# ── Read: freshness_basis ────────────────────────────────────────────────────


def _row(**fields: object) -> SimpleNamespace:
    base: dict = dict(
        date_posted="",
        date_confidence="",
        date_found=_days_ago(100),
        date_updated="",
        last_seen_at=None,
        url_status="unknown",
        last_checked_at=None,
    )
    base.update(fields)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "fields, basis",
    [
        (dict(date_posted=_iso(_days_ago(10))), "posted"),
        (dict(date_posted=_iso(_days_ago(120)), date_updated=_iso(_days_ago(3))), "updated"),
        (dict(date_posted=_iso(_days_ago(120)), last_seen_at=_days_ago(2)), "listed"),
        # SQLite hands datetimes back naive; naive means UTC.
        (
            dict(date_posted=_iso(_days_ago(120)), last_seen_at=_days_ago(2).replace(tzinfo=None)),
            "listed",
        ),
        (
            dict(date_posted=_iso(_days_ago(120)), url_status="alive", last_checked_at=_days_ago(5)),
            "verified_open",
        ),
        (
            dict(
                date_posted=_iso(_days_ago(120)),
                url_status="alive",
                last_checked_at=_days_ago(60),
                last_seen_at=_days_ago(60),
            ),
            None,
        ),
        (
            dict(date_posted=_iso(_days_ago(120)), url_status="dead", last_checked_at=_days_ago(5)),
            None,
        ),
        # Order of evidence: an edit outranks a listing, a listing outranks a link check.
        (
            dict(
                date_posted=_iso(_days_ago(120)),
                date_updated=_iso(_days_ago(3)),
                last_seen_at=_days_ago(2),
                url_status="alive",
                last_checked_at=_days_ago(1),
            ),
            "updated",
        ),
        (
            dict(
                date_posted=_iso(_days_ago(120)),
                last_seen_at=_days_ago(2),
                url_status="alive",
                last_checked_at=_days_ago(1),
            ),
            "listed",
        ),
        # Unknown date: no basis. The gate keeps the row on its own path.
        (dict(date_posted=""), None),
        (dict(date_posted="recently"), None),
    ],
)
def test_freshness_basis_names_the_strongest_evidence(fields: dict, basis: str | None) -> None:
    from app.services.freshness import freshness_basis

    assert freshness_basis(_row(**fields), WINDOW, now=NOW) == basis


def test_freshness_basis_reads_relative_prose_against_the_scrape_anchor() -> None:
    from app.services.freshness import freshness_basis

    said_three_days_ago_at_scrape = _row(
        date_posted="Reposted 3 Days Ago", date_found=_days_ago(6)
    )
    assert freshness_basis(said_three_days_ago_at_scrape, WINDOW, now=NOW) == "posted"
    assert freshness_basis(said_three_days_ago_at_scrape, 7, now=NOW) is None


# ── Board gate: _search_work_uncached and the profile-work API ───────────────


def _make_db(tmp_path, monkeypatch):
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
    db.add(
        Workspace(
            id="local", name="Local", slug="local",
            last_active_at=now, expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(["Data Engineering Manager", "Data Engineering Lead"]),
            keywords_json=json.dumps([]),
            workplace_preference="remote_friendly",
            max_days_old=WINDOW,
        )
    )
    db.commit()
    return db, generator


def _add_row(db, *, title: str, company: str, url: str, posted_days_ago: int | None, **fields):
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    posted = "" if posted_days_ago is None else _iso(_days_ago(posted_days_ago, now=now))
    row = ApplicationRecord(
        job_title=title,
        company=company,
        job_url=url,
        location="Los Angeles, CA",
        state_codes=",CA,",
        remote_scope="us",
        is_remote=False,
        source="greenhouse",
        vertical="career",
        date_posted=posted,
        date_confidence="exact" if posted else "missing",
        date_found=_days_ago(min(posted_days_ago or 0, 100), now=now),
        **fields,
    )
    db.add(row)
    db.commit()
    return row


def test_board_keeps_an_old_row_the_pull_listed_yesterday(tmp_path, monkeypatch) -> None:
    from app.api.applications import list_profile_work
    from app.services import local_agent_service as las

    db, generator = _make_db(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        natera = _add_row(
            db, title=NATERA_TITLE, company="Natera", url=NATERA_URL,
            posted_days_ago=120, last_seen_at=now - timedelta(days=1),
        )
        _add_row(
            db, title=STRIPE_TITLE, company="Stripe", url="https://stripe.com/jobs/1",
            posted_days_ago=120, last_seen_at=now - timedelta(days=60),
        )
        unknown = _add_row(
            db, title="Lead Data Engineer", company="Undated Co",
            url="https://undated.example/1", posted_days_ago=None,
        )

        result = las._search_work_uncached(db, browse_all=True, page_size=50, workspace_id="local")
        by_id = {row["opportunity_id"]: row for row in result["results"]}
        assert set(by_id) == {natera.id, unknown.id}
        assert by_id[natera.id]["freshness_basis"] == "listed"
        assert by_id[unknown.id]["freshness_basis"] is None
        assert result["freshness_filter_summary"]["known_stale_excluded"] == 1

        response = list_profile_work(
            search=None,
            location=None,
            location_strict=False,
            salary_min=None,
            salary_max=None,
            is_remote=None,
            posted_within_days=None,
            source_category=None,
            page=1,
            page_size=24,
            workspace=SimpleNamespace(workspace=SimpleNamespace(id="local")),
            db=db,
        )
        cards = {item.company: item for item in response.items}
        assert set(cards) == {"Natera", "Undated Co"}
        assert cards["Natera"].freshness_basis == "listed"
        assert cards["Natera"].date_posted.startswith(_iso(_days_ago(120, now=now))[:10])
        assert cards["Undated Co"].freshness_basis is None
    finally:
        generator.close()


def test_board_carries_posted_updated_and_verified_open_bases(tmp_path, monkeypatch) -> None:
    from app.services import local_agent_service as las

    db, generator = _make_db(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        fresh = _add_row(
            db, title="Data Engineering Manager", company="Fresh Co",
            url="https://fresh.example/1", posted_days_ago=10,
        )
        edited = _add_row(
            db, title=STRIPE_TITLE, company="Stripe", url="https://stripe.com/jobs/1",
            posted_days_ago=120, date_updated=_iso(_days_ago(1, now=now)),
        )
        alive = _add_row(
            db, title="Lead Data Engineer", company="Checked Co",
            url="https://checked.example/1", posted_days_ago=120,
            url_status="alive", last_checked_at=now - timedelta(days=5),
        )

        result = las._search_work_uncached(db, browse_all=True, page_size=50, workspace_id="local")
        bases = {row["opportunity_id"]: row["freshness_basis"] for row in result["results"]}
        assert bases == {fresh.id: "posted", edited.id: "updated", alive.id: "verified_open"}
        assert result["freshness_filter_summary"]["known_stale_excluded"] == 0
    finally:
        generator.close()


def test_mcp_search_work_payload_carries_the_basis_without_changing_shape(
    tmp_path, monkeypatch,
) -> None:
    from app.services import local_agent_service as las

    db, generator = _make_db(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        _add_row(
            db, title=NATERA_TITLE, company="Natera", url=NATERA_URL,
            posted_days_ago=120, last_seen_at=now - timedelta(days=1),
        )
        result = las._search_work_uncached(db, page_size=20, workspace_id="local")
        (item,) = result["results"]
        assert item["organization"] == "Natera"
        assert item["freshness"]["basis"] == "listed"
        assert item["freshness"]["source_posted_at"]
    finally:
        generator.close()


def test_an_explicit_posted_window_means_the_posted_date(tmp_path, monkeypatch) -> None:
    """Oct 6 2026: the assistant's search_work(posted_within_days=7) came back
    with 274 rows while the board's toolbar showed 26, because the still-open
    evidence (listed, verified open) was satisfying an explicit posted window.
    An explicit window is about the posted date; the saved window keeps the
    still-open rule."""
    from app.services import local_agent_service as las

    db, generator = _make_db(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        old_listed = _add_row(
            db, title=NATERA_TITLE, company="Natera", url=NATERA_URL,
            posted_days_ago=120, last_seen_at=now - timedelta(days=1),
            url_status="alive", last_checked_at=now - timedelta(days=1),
        )
        fresh = _add_row(
            db, title="Lead Data Engineer", company="Fresh Co",
            url="https://fresh.example/1", posted_days_ago=3,
        )

        explicit = las._search_work_uncached(
            db, browse_all=True, page_size=50, workspace_id="local", posted_within_days=7,
        )
        assert {row["opportunity_id"] for row in explicit["results"]} == {fresh.id}
        assert explicit["freshness_filter_summary"]["known_stale_excluded"] == 1

        saved = las._search_work_uncached(db, browse_all=True, page_size=50, workspace_id="local")
        by_id = {row["opportunity_id"]: row for row in saved["results"]}
        assert set(by_id) == {old_listed.id, fresh.id}
        assert by_id[old_listed.id]["freshness_basis"] == "listed"
    finally:
        generator.close()
