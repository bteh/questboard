"""A US city preference must not hide US-nationwide postings.

A row whose location is a bare country ("United States") is reachable from
any US city, but the place filter only recognized the literal words
remote/online/nationwide/anywhere, so a seeker who saved "Los Angeles" lost
every national US posting (the reported BILL case: US-wide Staff Data
Engineer roles vanished). A specific out-of-metro city ("New York, United
States") must still be filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path):
    from job_finder.models.database import Base, ApplicationRecord  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add(s, title, location, is_remote=False, remote_scope=None):
    from job_finder.models.database import ApplicationRecord

    row = ApplicationRecord(
        job_title=title,
        company="BILL" if "Staff" in title else "Acme",
        job_url=f"https://x.example/{title.replace(' ', '-')}",
        location=location,
        is_remote=is_remote,
        remote_scope=remote_scope,
        vertical="career",
    )
    s.add(row)
    s.flush()
    return row


def _matches(s, location, strict=False):
    from app.services.application_service import place_filter
    from job_finder.models.database import ApplicationRecord

    cond = place_filter(ApplicationRecord, location, location_strict=strict)
    q = s.query(ApplicationRecord)
    if cond is not None:
        q = q.filter(cond)
    return {r.job_title for r in q.all()}


def test_us_city_keeps_nationwide_us_postings(session):
    _add(session, "Senior Staff Data Engineer", "United States")
    _add(session, "Staff Data Warehouse Engineer",
         "Draper, Utah, United States; San Jose, California, United States; United States")
    _add(session, "LA Data Engineer", "Los Angeles, CA")
    got = _matches(session, "Los Angeles")
    assert "Senior Staff Data Engineer" in got
    assert "Staff Data Warehouse Engineer" in got
    assert "LA Data Engineer" in got


def test_specific_other_city_still_filtered(session):
    _add(session, "NYC only role", "New York, United States")
    _add(session, "Nationwide role", "United States")
    got = _matches(session, "Los Angeles")
    assert "Nationwide role" in got
    assert "NYC only role" not in got


def test_usa_and_us_country_forms_count_as_nationwide(session):
    _add(session, "USA role", "USA")
    _add(session, "US role", "US")
    _add(session, "Full name role", "United States of America")
    got = _matches(session, "Los Angeles")
    assert got == {"USA role", "US role", "Full name role"}


def test_strict_near_me_still_drops_nationwide(session):
    _add(session, "Nationwide role", "United States")
    _add(session, "LA role", "Culver City, CA")
    got = _matches(session, "Los Angeles", strict=True)
    assert "Nationwide role" not in got
    assert "LA role" in got
