"""A source still scanning at the pool deadline keeps the rows it already has.

Real case (Brian, Sep 9 2026): Greenhouse (308 company boards), Lever (251)
and Ashby (387) return 700-1200 rows each when they finish, but blew the
shared 60-second pool deadline on 2 of 5 runs. Each time the run log said
"timeout, 0 rows" and the rows from the first ~250 boards were discarded.
Those direct-employer rows are the best supply on the board.

Rule under test: the registry hands each source a ``partial_sink``; a
source that fans out over many boards publishes each board's rows into it
as they land. When the deadline hits, whatever is in the sink is kept and
the source is recorded as ``partial`` with the real row count.
"""

from __future__ import annotations

import importlib
import threading
from unittest.mock import patch

registry_module = importlib.import_module("job_finder.tools.scrapers._registry")
ScraperMeta = registry_module.ScraperMeta
run_scrapers = registry_module.run_scrapers


def _row(source: str, i: int) -> dict:
    return {
        "title": f"Data Engineering Manager {i}",
        "company": f"Employer {i}",
        "location": "Los Angeles, CA",
        "url": f"https://{source}.example/{i}",
        "source": source,
        "description": "Lead the data platform team.",
    }


def test_slow_source_keeps_rows_fetched_before_the_deadline() -> None:
    blocker = threading.Event()
    recorded: list[dict] = []
    receipt: list[dict] = []

    def slow(*, partial_sink, **_kwargs):
        for i in range(3):
            partial_sink.append(_row("slow", i))
        blocker.wait(10)
        return []

    registry = {
        "slow": ScraperMeta(
            name="slow", display_name="Slow ATS", url="https://slow.example",
            description="", category="ats", enabled_by_default=True,
            search_fn=slow,
        ),
    }
    from job_finder.models import database as database_module

    try:
        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(registry_module, "_SCRAPER_POOL_TIMEOUT_SECONDS", 0.2), \
             patch.object(database_module, "record_scrape_runs", side_effect=recorded.extend):
            jobs = run_scrapers(names=["slow"], roles=["data engineering manager"], outcome_sink=receipt)
    finally:
        blocker.set()

    assert sorted(job["url"] for job in jobs) == [
        "https://slow.example/0",
        "https://slow.example/1",
        "https://slow.example/2",
    ]
    outcome = receipt[0]
    assert outcome["source"] == "slow"
    assert outcome["finish_reason"] == "partial"
    assert outcome["rows_found"] == 3
    assert "deadline" in outcome["error_sample"]
    assert recorded[0]["finish_reason"] == "partial"
    assert recorded[0]["rows_found"] == 3


def test_source_that_never_published_is_still_a_timeout() -> None:
    blocker = threading.Event()
    receipt: list[dict] = []

    def hung(**_kwargs):
        blocker.wait(10)
        return []

    registry = {
        "hung": ScraperMeta(
            name="hung", display_name="Hung", url="https://hung.example",
            description="", category="general", enabled_by_default=True,
            search_fn=hung,
        ),
    }
    from job_finder.models import database as database_module

    try:
        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(registry_module, "_SCRAPER_POOL_TIMEOUT_SECONDS", 0.05), \
             patch.object(database_module, "record_scrape_runs", lambda _rows: None):
            jobs = run_scrapers(names=["hung"], outcome_sink=receipt)
    finally:
        blocker.set()

    assert jobs == []
    assert receipt[0]["finish_reason"] == "timeout"
    assert receipt[0]["rows_found"] == 0


def test_greenhouse_publishes_each_board_into_the_sink_as_it_lands() -> None:
    greenhouse = importlib.import_module("job_finder.tools.scrapers.greenhouse")
    sink: list[dict] = []

    def fake_fetch(slug, roles, **_kwargs):
        return [_row("greenhouse", int(slug[-1]))]

    with patch.object(greenhouse, "_fetch_company_jobs", side_effect=fake_fetch):
        jobs = greenhouse.search_greenhouse(
            roles=["data engineering manager"],
            max_results=50,
            companies=["board0", "board1", "board2"],
            partial_sink=sink,
        )

    assert len(jobs) == 3
    assert sorted(row["url"] for row in sink) == sorted(row["url"] for row in jobs)


def test_lever_publishes_each_board_into_the_sink_as_it_lands() -> None:
    lever = importlib.import_module("job_finder.tools.scrapers.lever")
    sink: list[dict] = []

    def fake_fetch(slug, roles, **_kwargs):
        return [_row("lever", int(slug[-1]))]

    with patch.object(lever, "_fetch_company_postings", side_effect=fake_fetch):
        jobs = lever.search_lever(
            roles=["data engineering manager"],
            max_results=50,
            companies=["board0", "board1", "board2"],
            partial_sink=sink,
        )

    assert len(jobs) == 3
    assert sorted(row["url"] for row in sink) == sorted(row["url"] for row in jobs)


def test_ashby_publishes_each_board_into_the_sink_as_it_lands() -> None:
    ashby = importlib.import_module("job_finder.tools.scrapers.ashby")
    sink: list[dict] = []

    def fake_fetch(slug, roles, **_kwargs):
        return [_row("ashby", int(slug[-1]))]

    with patch.object(ashby, "_fetch_company_jobs", side_effect=fake_fetch):
        jobs = ashby.search_ashby(
            roles=["data engineering manager"],
            max_results=50,
            companies=["board0", "board1", "board2"],
            partial_sink=sink,
        )

    assert len(jobs) == 3
    assert sorted(row["url"] for row in sink) == sorted(row["url"] for row in jobs)


def test_workable_publishes_each_board_into_the_sink_as_it_lands() -> None:
    workable = importlib.import_module("job_finder.tools.scrapers.workable")
    sink: list[dict] = []

    def fake_fetch(slug, roles, **_kwargs):
        return [_row("workable", int(slug[-1]))]

    with patch.object(workable, "_fetch_company_jobs", side_effect=fake_fetch):
        jobs = workable.search_workable(
            roles=["data engineering manager"],
            max_results=50,
            companies=["board0", "board1", "board2"],
            partial_sink=sink,
        )

    assert len(jobs) == 3
    assert sorted(row["url"] for row in sink) == sorted(row["url"] for row in jobs)


def test_workday_publishes_each_employer_into_the_sink_as_it_lands() -> None:
    workday = importlib.import_module("job_finder.tools.scrapers.workday")
    sink: list[dict] = []
    employers = {
        f"employer{i}": {
            "name": f"Employer {i}", "tenant": f"employer{i}",
            "site_id": "Careers", "base_url": f"https://employer{i}.wd1.myworkdayjobs.com",
        }
        for i in range(3)
    }

    def fake_search(key, employer, roles, max_results, **_kwargs):
        return [_row("workday", int(key[-1]))]

    with patch.object(workday, "_load_employers", return_value=employers), \
         patch.object(workday, "_search_employer", side_effect=fake_search):
        jobs = workday.search_workday(
            roles=["data engineering manager"],
            max_results=50,
            partial_sink=sink,
        )

    assert len(jobs) == 3
    assert sorted(row["url"] for row in sink) == sorted(row["url"] for row in jobs)
