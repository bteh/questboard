"""Rows an ATS mislabelled remote have to be re-judged, not left standing.

Ashby's `isRemote` is true on every hybrid posting, and the scraper used to
read it before `workplaceType`. Worse, it stamped `remote_flag_reported`,
which company_classifier treats as definitive: a reported flag skips both the
description scan for hybrid wording and the rule that a board-reported remote
flag on a job with a street address deserves skepticism.

So the classifier's own judgment was suppressed rather than wrong. This repair
re-runs it with the flag off, which is why it calls classify_work_type instead
of writing a second remote-detection rule.

The re-scrape path cannot do this job: it refreshes location, date_posted and
state_codes on an existing row but never is_remote, so 141 of 173 Ashby rows
on the live board would have stayed wrong forever.

Real cases from that board, all flagged remote:
    Plaid    Staff SWE, Data Infrastructure   San Francisco HQ
    Abridge  Senior Data Engineer             SF Office
    42Dot    LLM Engineer                     Pangyo, South Korea
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.models.remote_flag_repair import (  # noqa: E402
    REMOTE_FLAG_REPAIR_NAME,
    REMOTE_FLAG_REPAIR_VERSION,
    repair_remote_flags,
)

STAMP = "2026-07-01T00:00:00+00:00"


@pytest.fixture()
def engine(tmp_path):
    """A temp DB. Never the live one: the desktop runtime's database is a
    symlink to backend/data/job_tracker.db, so a test that opens the default
    path writes the user's real board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, job_title VARCHAR, company VARCHAR,"
            " location VARCHAR, description TEXT, source VARCHAR,"
            " vertical VARCHAR, is_remote BOOLEAN, work_type VARCHAR,"
            " updated_at VARCHAR)"
        ))
    return eng


def _add(engine, **kw):
    row = {
        "job_title": "Manager, Data Engineering", "company": "Airwallex",
        "location": "US - San Francisco", "description": "", "source": "ashby",
        "vertical": "career", "is_remote": 1, "work_type": "remote",
        "updated_at": STAMP,
    }
    row.update(kw)
    cols = ", ".join(row)
    binds = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO applications ({cols}) VALUES ({binds})"), row)


def _rows(engine):
    with engine.begin() as conn:
        return list(conn.execute(text(
            "SELECT company, location, is_remote, work_type, updated_at"
            " FROM applications ORDER BY id"
        )))


def test_the_airwallex_row_stops_claiming_remote(engine):
    """The posting the user reported: hybrid, San Francisco, on a Los Angeles
    + remote board."""
    _add(engine)
    assert repair_remote_flags(engine) == 1

    company, location, is_remote, work_type, _ = _rows(engine)[0]
    assert not is_remote
    assert work_type != "remote"


def test_a_genuinely_remote_row_is_left_alone(engine):
    _add(engine, company="GitLab", location="Remote, US")
    assert repair_remote_flags(engine) == 0
    assert _rows(engine)[0][2]


def test_a_remote_row_confirmed_by_its_description_survives(engine):
    """The repair must not strip remote from a job that says so in its text
    merely because it also names an office."""
    _add(
        engine,
        company="Sentry",
        location="San Francisco, California",
        description="This is a fully remote position; you may work from anywhere in the US.",
    )
    assert repair_remote_flags(engine) == 0
    assert _rows(engine)[0][2]


def test_rows_from_other_sources_are_untouched(engine):
    """Only Ashby ever stamped the definitive flag, so only Ashby rows were
    denied the classifier's judgment."""
    _add(engine, company="Disney", source="linkedin", location="Burbank, CA")
    assert repair_remote_flags(engine) == 0
    assert _rows(engine)[0][2]


def test_side_quests_are_untouched(engine):
    _add(engine, vertical="side_quest", location="San Francisco, CA")
    assert repair_remote_flags(engine) == 0


def test_the_repair_does_not_reshuffle_the_board(engine):
    """updated_at orders the user's log. A data repair must not reorder it."""
    _add(engine)
    repair_remote_flags(engine)
    assert _rows(engine)[0][4] == STAMP


def test_a_second_run_is_a_no_op(engine):
    _add(engine)
    assert repair_remote_flags(engine) == 1
    _add(engine, company="Plaid", location="San Francisco HQ")
    assert repair_remote_flags(engine) == 0, "version marker should skip the scan"


def test_force_rescans_after_the_marker_is_set(engine):
    _add(engine)
    repair_remote_flags(engine)
    _add(engine, company="Plaid", location="San Francisco HQ")
    assert repair_remote_flags(engine, force=True) == 1


def test_the_marker_records_the_current_version(engine):
    _add(engine)
    repair_remote_flags(engine)
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT version FROM data_repairs WHERE name = :n"),
            {"n": REMOTE_FLAG_REPAIR_NAME},
        ).scalar()
    assert version == REMOTE_FLAG_REPAIR_VERSION


def test_a_database_without_the_table_does_not_crash(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert repair_remote_flags(eng) == 0
