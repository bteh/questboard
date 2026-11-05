"""Alive stamps given to closed jobs that redirected to a listing index get re-checked.

Real case (Brian's board, Nov 5 2026): until dead_redirect learned the
job-identity rule, a closed job that redirected to a careers index answered
200 and was stamped alive. The stamp (freshness basis "verified_open") kept it
on the board forever: 15 of 15 sampled stale Himalayas rows landed on
himalayas.app/jobs, 5 of 10 Greenhouse rows on a careers index. Those stamps
sit on any host, so repair v2 resets alive rows whose board presence rests on
the stamp alone (source date and last pull older than 45 days), and leaves rows
with any other freshness evidence alone.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from job_finder.models.link_status_repair import (  # noqa: E402
    LINK_STATUS_REPAIR_NAME,
    repair_link_status,
)

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-11-01 04:19:02.061323"
UPDATED = "2026-09-20T00:00:00+00:00"
FISCALNOTE = (
    "https://himalayas.app/companies/fiscalnote/jobs/"
    "director-data-analytics-business-intelligence"
)
THREE_CLOUD = "https://job-boards.greenhouse.io/3cloud/jobs/8682596002?gh_jid=8682596002"
DESCRIPT = "https://boards.greenhouse.io/descript/jobs/7780518003?gh_jid=7780518003"


@pytest.fixture()
def engine(tmp_path):
    """Temp DB only; the desktop runtime's DB is a symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, job_url VARCHAR, url_status VARCHAR,"
            " last_checked_at DATETIME, updated_at VARCHAR, date_posted VARCHAR,"
            " date_updated VARCHAR, last_seen_at DATETIME)"
        ))
    return eng


def _seed(
    engine,
    job_url: str,
    *,
    posted: str | None,
    seen: str | None = None,
    edited: str | None = None,
    status: str = "alive",
) -> int:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO applications (job_url, url_status, last_checked_at,"
                " updated_at, date_posted, date_updated, last_seen_at)"
                " VALUES (:u, :s, :c, :t, :p, :e, :l)"
            ),
            {"u": job_url, "s": status, "c": STAMP, "t": UPDATED, "p": posted, "e": edited, "l": seen},
        )
        return int(conn.execute(text("SELECT max(id) FROM applications")).scalar())


def _row(engine, row_id: int) -> tuple:
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT url_status, last_checked_at, updated_at FROM applications WHERE id = :i"),
            {"i": row_id},
        ).one()


def _mark_v1_applied(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE data_repairs (name VARCHAR(64) PRIMARY KEY,"
            " version INTEGER NOT NULL, applied_at VARCHAR(40) DEFAULT '')"
        ))
        conn.execute(
            text("INSERT INTO data_repairs (name, version) VALUES (:n, 1)"),
            {"n": LINK_STATUS_REPAIR_NAME},
        )


def test_v2_resets_stamp_only_rows_on_any_host_after_v1_already_ran(engine) -> None:
    _mark_v1_applied(engine)
    fiscalnote = _seed(engine, FISCALNOTE, posted="2026-06-02", seen="2026-07-01 00:00:00")
    three_cloud = _seed(engine, THREE_CLOUD, posted="2026-05-10T00:00:00Z")

    assert repair_link_status(engine, now=NOW) == 2

    assert _row(engine, fiscalnote) == ("unknown", None, UPDATED)
    assert _row(engine, three_cloud) == ("unknown", None, UPDATED)


def test_v2_keeps_rows_with_other_freshness_evidence(engine) -> None:
    _mark_v1_applied(engine)
    recent_post = _seed(engine, DESCRIPT, posted="2026-10-20")
    recent_pull = _seed(engine, FISCALNOTE, posted="2026-06-02", seen="2026-11-04 00:00:00")
    recent_edit = _seed(engine, THREE_CLOUD, posted="2026-05-10", edited="2026-10-30")
    prose_date = _seed(engine, FISCALNOTE + "-2", posted="Reposted 3 Days Ago")
    no_date = _seed(engine, FISCALNOTE + "-3", posted=None)
    already_dead = _seed(engine, THREE_CLOUD + "&x=1", posted="2026-05-10", status="dead")

    assert repair_link_status(engine, now=NOW) == 0

    for row_id in (recent_post, recent_pull, recent_edit, prose_date, no_date):
        assert _row(engine, row_id) == ("alive", STAMP, UPDATED)
    assert _row(engine, already_dead) == ("dead", STAMP, UPDATED)


def test_v2_runs_once(engine) -> None:
    _seed(engine, FISCALNOTE, posted="2026-06-02")

    assert repair_link_status(engine, now=NOW) == 1
    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET url_status = 'alive', last_checked_at = :c"), {"c": STAMP})
    assert repair_link_status(engine, now=NOW) == 0
