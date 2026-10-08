"""Contract tests for the part-time shift source (parttime kind, JobSpy Indeed).

Fixture is 36 REAL rows from job_search_tool.search_jobs for barista,
server, and cashier, Indeed only, job_type=parttime, 10 miles around
"Koreatown, Los Angeles, CA", captured live 2026-10-08 (descriptions
trimmed). Edge rows the live part-time filter never returned are built
inline. No live HTTP.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "indeed_parttime_rows.json"
CAPTURED = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture()
def mod():
    from job_finder.tools.scrapers import indeed_parttime

    return indeed_parttime


@pytest.fixture()
def raw() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _row(**kw) -> dict:
    base = {
        "title": "Barista",
        "company": "Cafe",
        "location": "Los Angeles, CA, US",
        "url": "https://www.indeed.com/viewjob?jk=edge",
        "source": "indeed",
        "description": "",
        "salary_min": None,
        "salary_max": None,
        "salary_period": "hourly",
        "salary_currency": "USD",
        "date_posted": "2026-10-07",
        "is_remote": False,
        "job_type": "parttime",
    }
    base.update(kw)
    return base


def test_keeps_every_real_row_once(mod, raw) -> None:
    rows = mod.filter_rows(raw, 100, now=CAPTURED)
    # 36 captured rows: 85C and the boba shop came back under two terms
    # (same URL). Panini Kabob Grill's twin ads stay: Inglewood and Glendale.
    assert len(rows) == 34
    assert len({r["url"] for r in rows}) == 34
    assert all(r["vertical"] == "parttime" and r["source"] == "indeed-parttime" for r in rows)
    assert all(r["url"].startswith("https://www.indeed.com/viewjob?jk=") for r in rows)
    assert not any(r["is_remote"] for r in rows)


def test_pay_only_when_indeed_states_an_amount(mod, raw) -> None:
    rows = {r["url"]: r for r in mod.filter_rows(raw, 100, now=CAPTURED)}
    ralphs = next(
        r for r in rows.values() if r["title"] == "Starbucks Barista" and r["company"] == "Ralphs"
    )
    assert (ralphs["salary_min"], ralphs["salary_max"], ralphs["salary_period"]) == (18.0, 24.0, "hourly")
    assert ralphs["salary_source"] == "reported"
    sodexo = next(r for r in rows.values() if r["company"] == "Sodexo")
    # Indeed says "hourly" with no amount: no pay, no period
    assert "salary_min" not in sodexo and "salary_period" not in sodexo


def test_mixed_part_and_full_time_rows_stay(mod) -> None:
    assert mod.keep_row(_row(job_type="parttime, fulltime"))
    assert mod.keep_row(_row(job_type="parttime, contract"))
    assert mod.keep_row(_row(job_type=""))


def test_full_time_only_rows_drop(mod) -> None:
    assert not mod.keep_row(_row(job_type="fulltime"))
    assert not mod.keep_row(_row(job_type="fulltime, contract"))
    # live probe without the filter: "BARISTA (FULL TIME)", Wolfgang Puck Catering
    assert not mod.keep_row(_row(title="BARISTA (FULL TIME)", job_type=""))
    assert mod.keep_row(_row(title="Barista, full-time or part-time"))


def test_salaried_manager_titles_drop(mod) -> None:
    for title in (
        "Restaurant Manager",
        "Assistant Store Manager",
        "Cafe Supervisor",
        "Sous Chef",
        "District Manager, Boba",
    ):
        assert not mod.keep_row(_row(title=title)), title
    # hourly leads are shift work, not salaried management
    assert mod.keep_row(_row(title="Boba Tea Shift Lead"))
    assert not mod.keep_row(_row(salary_min=52000.0, salary_period="yearly"))


def test_same_ad_same_place_under_a_new_url_drops(mod) -> None:
    twins = [
        _row(url="https://www.indeed.com/viewjob?jk=a"),
        _row(url="https://www.indeed.com/viewjob?jk=b"),
    ]
    assert len(mod.filter_rows(twins, 10, now=CAPTURED)) == 1


def test_remote_and_old_rows_drop(mod) -> None:
    assert mod.filter_rows([_row(is_remote=True)], 10, now=CAPTURED) == []
    assert mod.filter_rows([_row(date_posted="2026-09-01")], 10, now=CAPTURED) == []
    assert len(mod.filter_rows([_row(date_posted="")], 10, now=CAPTURED)) == 1


def test_search_runs_each_term_near_the_place_with_the_part_time_filter(mod, raw) -> None:
    calls: list[dict] = []

    def fake_search_jobs(**kw):
        calls.append(kw)
        return raw if kw["search_term"] == "barista" else []

    with patch("job_finder.tools.job_search_tool.search_jobs", fake_search_jobs):
        rows = mod.search_indeed_parttime(place="Koreatown, Los Angeles, CA", max_days_old=3650)

    assert [c["search_term"] for c in calls] == list(mod.SEARCH_TERMS)
    for c in calls:
        assert c["location"] == "Koreatown, Los Angeles, CA"
        assert c["boards"] == ["indeed"]
        assert c["job_type"] == "parttime"
        assert c["distance"] == 10
        # Indeed drops job_type whenever a posted-within window is sent
        assert c["hours_old"] is None
    assert len(rows) == 34


@pytest.mark.parametrize("place", [None, "", "  ", "Remote", "United States"])
def test_no_saved_place_means_no_fetch(mod, place) -> None:
    with patch("job_finder.tools.job_search_tool.search_jobs") as fake:
        assert mod.search_indeed_parttime(place=place) == []
    fake.assert_not_called()


def test_registered_in_the_parttime_lane(mod) -> None:
    from job_finder.tools.scrapers._registry import get_registry

    meta = get_registry()["indeed-parttime"]
    assert meta.vertical == "parttime"
    assert meta.refresh_hours and meta.stale_after_days
    assert not meta.research_only
    assert meta.allowed_url_hosts == ("indeed.com",)


def test_place_reaches_only_sources_that_declare_it() -> None:
    from job_finder.quests import _accepted_geo_kwargs
    from job_finder.tools.scrapers.indeed_parttime import search_indeed_parttime
    from job_finder.tools.scrapers.reddit_lajobs import search_reddit_lajobs

    geo = {"query": None, "lat": None, "lon": None, "radius_miles": None, "place": "Koreatown"}
    assert _accepted_geo_kwargs(search_indeed_parttime, geo) == {"place": "Koreatown"}
    assert _accepted_geo_kwargs(search_reddit_lajobs, geo) == {}
