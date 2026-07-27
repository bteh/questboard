"""Rows stored with no description never get a second chance on their own.

Real report, 2026-07-27: a Walt Disney row read "REWARD not stated" while its
LinkedIn page states $171,600-$252,000, because the row was saved with an
empty description. Reordering the in-run backfill stops NEW rows landing that
way, but it cannot help rows already on the board: a stored row is deduped away
before the pull's backfill ever sees it. 35 of 53 LinkedIn rows and 18 of 28
BuiltIn rows were stuck like that.

This repair refetches them and re-runs the same salary parser a fresh pull
would. Two rules it must never break, both learned the hard way:

- Reported pay is never overwritten. A scraper that told us the band wins over
  anything parsed out of prose.
- A failed fetch changes nothing. An earlier salary repair filled rows from
  text that did not mean pay ("50,000 articles" became $50k) and poisoned the
  board; a repair that writes on missing data is worse than one that does
  nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

DISNEY = (
    "Technology is at the heart of Disney's past, present and future. "
    "The hiring range for this position in Glendale, CA is $171,600 to "
    "$252,000 per year. The base pay actually offered may vary."
)


@pytest.fixture()
def maintenance():
    """Resolve the module at test time, and patch on that same object.

    Many API tests re-import `job_finder.models.*` under their own temp DB, so
    a module-level import here binds a different object than a
    patch("job_finder.models.maintenance...") string would resolve later. When
    those two drift the stub silently misses, and these tests fetched LinkedIn
    for real instead of failing loudly.
    """
    from job_finder.models import maintenance as module

    return module


@pytest.fixture()
def engine(tmp_path):
    """A temp DB. Never point a repair test at the runtime database: it is a
    symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            "id INTEGER PRIMARY KEY, job_title TEXT, company TEXT, source TEXT,"
            "job_url TEXT, description TEXT, vertical TEXT, url_status TEXT,"
            "salary_min FLOAT, salary_max FLOAT, salary_currency TEXT,"
            "salary_period TEXT, salary_min_annualized FLOAT,"
            "salary_max_annualized FLOAT, salary_source TEXT)"
        ))
    return eng


def _add(engine, **kw):
    cols = {
        "job_title": "Manager, Software Engineering",
        "company": "The Walt Disney Company",
        "source": "linkedin",
        "job_url": "https://www.linkedin.com/jobs/view/4433613222",
        "description": "",
        "vertical": "career",
        "url_status": "",
        "salary_min": None,
        "salary_max": None,
    }
    cols.update(kw)
    names = ", ".join(cols)
    binds = ", ".join(f":{k}" for k in cols)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO applications ({names}) VALUES ({binds})"), cols)


def _row(engine, row_id=1):
    with engine.begin() as conn:
        return conn.execute(text(
            "SELECT description, salary_min, salary_max, salary_source "
            "FROM applications WHERE id = :i"
        ), {"i": row_id}).fetchone()


def test_fills_the_description_and_reads_the_pay_out_of_it(maintenance, engine):
    _add(engine)
    with patch.object(maintenance, "_fetch_description", return_value=DISNEY):
        assert maintenance.refetch_missing_descriptions(engine) == 1

    description, smin, smax, source = _row(engine)
    assert "Glendale" in description
    assert (smin, smax) == (171600.0, 252000.0)
    assert source == "parsed_from_description"


def test_a_failed_fetch_leaves_the_row_exactly_as_it_was(maintenance, engine):
    _add(engine)
    with patch.object(maintenance, "_fetch_description", return_value=""):
        assert maintenance.refetch_missing_descriptions(engine) == 0

    description, smin, smax, source = _row(engine)
    assert description == ""
    assert smin is None and smax is None and not source


def test_reported_pay_is_never_overwritten(maintenance, engine):
    """The scraper said 300-340k. Prose in the page must not replace that."""
    _add(engine, salary_min=300000.0, salary_max=340000.0, salary_source="reported")
    with patch.object(maintenance, "_fetch_description", return_value=DISNEY):
        maintenance.refetch_missing_descriptions(engine)

    description, smin, smax, source = _row(engine)
    assert "Glendale" in description, "the description is still worth having"
    assert (smin, smax) == (300000.0, 340000.0)
    assert source == "reported"


def test_a_description_with_no_pay_still_gets_stored(maintenance, engine):
    """Text is worth fetching for its own sake: the assistant ranks on it."""
    _add(engine)
    with patch.object(
        maintenance, "_fetch_description",
        return_value="We are a team of 150 engineers building great things.",
    ):
        assert maintenance.refetch_missing_descriptions(engine) == 1

    description, smin, smax, _ = _row(engine)
    assert "150 engineers" in description
    assert smin is None and smax is None


def test_rows_that_already_have_text_are_left_alone(maintenance, engine):
    _add(engine, description="Already here.")
    with patch.object(maintenance, "_fetch_description") as fetch:
        assert maintenance.refetch_missing_descriptions(engine) == 0
    fetch.assert_not_called()


def test_dead_and_quest_rows_are_not_refetched(maintenance, engine):
    _add(engine, url_status="dead")
    _add(engine, vertical="think", url_status="")
    with patch.object(maintenance, "_fetch_description") as fetch:
        assert maintenance.refetch_missing_descriptions(engine) == 0
    fetch.assert_not_called()


def test_a_row_with_no_url_is_skipped_rather_than_fetched(maintenance, engine):
    _add(engine, job_url="")
    with patch.object(maintenance, "_fetch_description") as fetch:
        assert maintenance.refetch_missing_descriptions(engine) == 0
    fetch.assert_not_called()


def test_the_limit_bounds_how_many_pages_one_run_fetches(maintenance, engine):
    for i in range(6):
        _add(engine, job_url=f"https://www.linkedin.com/jobs/view/{i}")
    with patch.object(
        maintenance, "_fetch_description", return_value=DISNEY,
    ) as fetch:
        assert maintenance.refetch_missing_descriptions(engine, limit=2) == 2
    assert fetch.call_count == 2


def test_one_bad_row_does_not_abort_the_rest(maintenance, engine):
    for i in range(3):
        _add(engine, job_url=f"https://www.linkedin.com/jobs/view/{i}")

    calls = {"n": 0}

    def flaky(source, url):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("connection reset")
        return DISNEY

    with patch.object(maintenance, "_fetch_description", side_effect=flaky):
        assert maintenance.refetch_missing_descriptions(engine) == 2


def test_a_source_with_no_fetcher_is_left_alone(maintenance, engine):
    """Only sources we know how to refetch are touched."""
    _add(engine, source="greenhouse", job_url="https://boards.greenhouse.io/x/jobs/1")
    with patch.object(maintenance, "_fetch_description") as fetch:
        assert maintenance.refetch_missing_descriptions(engine) == 0
    fetch.assert_not_called()


# ── pay usually sits at the BOTTOM of a long posting ─────────────────────────

def test_pay_below_the_storage_cap_is_still_extracted(maintenance, engine):
    """LinkedIn puts the hiring range last, after the duties.

    The real Disney row proved this: the refetch stored 3,000 characters of
    responsibilities and not one dollar figure, because the pay statement sat
    past the cut. Truncation is for storage; the parser must read the whole
    page or the cap silently decides which jobs have pay.
    """
    filler = "Partner with Program Managers to drive planning. " * 90
    full = filler + (
        " The hiring range for this position in Glendale, CA is "
        "$171,600 to $252,000 per year."
    )
    assert len(filler) > 3000, "the pay line has to fall past the cap"

    _add(engine)
    with patch.object(maintenance, "_fetch_description", return_value=full):
        assert maintenance.refetch_missing_descriptions(engine) == 1

    description, smin, smax, source = _row(engine)
    assert len(description) <= 3000, "storage stays capped"
    assert (smin, smax) == (171600.0, 252000.0)
    assert source == "parsed_from_description"
