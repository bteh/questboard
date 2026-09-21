"""Four defects the multi-model review found in the Sep 9-17 pull changes.

Each was reproduced by a reviewer against the real code; the fixture data
here is the minimal version of that reproduction.

1. A saved role can still lose its query. `_role_derived_terms` recognises
   a consolidated term only when it equals a saved role or that role's
   prefix-stripped base. When consolidation kept a different spelling for
   the group ("Director of Marketing" plus keyword "VP Marketing" keeps
   "vp marketing"), the survivor counts as a keyword and the cap can drop
   it, the very regression the cap change was meant to end.
2. Watchlist rows can be dropped at the scraper deadline. The partial sink
   holds the same dicts the scraper later strips of PROTECTED_ROW_KEY in
   cap_with_protected, so a deadline harvest re-caps without protection.
3. A source harvested at the deadline is reported as complete. The coverage
   receipt only knows timeout and exception as incomplete, so a "partial"
   outcome with rows shows state "ok" and loses its deadline note.
4. A harvested source runs its validation twice: its own thread finishes
   later, settles the full result again (validate + observe_jobs writes)
   and pushes to a queue nobody reads.
"""

from __future__ import annotations

import importlib
import threading
from unittest.mock import patch

import pytest

from job_finder.pipeline import (
    JobFinderPipeline,
    _cap_search_tasks,
    _consolidate_search_terms,
    _role_derived_terms,
    _source_coverage_entry,
)

registry_module = importlib.import_module("job_finder.tools.scrapers._registry")
ScraperMeta = registry_module.ScraperMeta
run_scrapers = registry_module.run_scrapers


# ── 1. role-derived terms survive a spelling swap ───────────────────────────

def test_a_role_kept_under_another_spelling_is_still_role_derived() -> None:
    saved = ["Director of Marketing"]
    merged = saved + ["VP Marketing"]  # the API path merges title-shaped keywords
    consolidated = _consolidate_search_terms(merged, [], config={"target_roles": saved})
    assert consolidated, "consolidation produced no query at all"
    role_terms = _role_derived_terms(consolidated, saved)
    # Whatever spelling consolidation kept for the marketing group stands in
    # for the saved role and must be protected from the cap.
    assert role_terms, f"no consolidated term protected for {saved}; got {consolidated}"
    tasks = [(t, loc) for loc in ["Los Angeles, CA", "Remote"] for t in consolidated]
    kept = _cap_search_tasks(tasks, cap=1, role_terms=role_terms)
    places_with_role = {loc for term, loc in kept if term in role_terms}
    assert places_with_role == {"Los Angeles, CA", "Remote"}


def test_a_role_absorbed_by_a_broader_keyword_stays_protected(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_search_jobs(*, search_term, is_remote, telemetry, **_kwargs):
        calls.append((search_term, bool(is_remote)))
        telemetry.update({"finish_reason": "zero_rows", "rows_found": 0, "duration_s": 0.01, "error_sample": ""})
        return []

    import job_finder.models.database as database_module
    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(database_module, "record_scrape_runs", lambda _rows: None)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])

    saved = ["Product Manager Operations"]
    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": ["indeed"],
        "additional_sources": [],
        "target_roles": saved,
        "keyword_searches": ["product manager", "data pipeline", "data products"],
        "search_settings": {"ai_expand_roles": False, "max_parallel_searches": 1, "max_search_tasks": 12, "max_unique_jobs": 100000, "max_days_old": 30},
        "location_preferences": {"include_remote": True},
    }
    pipeline.search_all_jobs(roles=saved + ["product manager", "data pipeline", "data products"], locations=["Los Angeles, CA", "Remote"])
    # "Product Manager Operations" is absorbed into the broader "product
    # manager" query; that query now stands in for the saved role and must
    # run in both places even under a cap that trims keyword queries.
    product_queries = {(term, remote) for term, remote in calls if "product manager" in term}
    assert {remote for _, remote in product_queries} == {False, True}, calls


# ── 2. watchlist rows survive the deadline harvest ──────────────────────────

def test_deadline_harvest_keeps_watchlist_rows_beyond_the_cap() -> None:
    from job_finder.tools.scrapers._utils import PROTECTED_ROW_KEY, cap_with_protected, publish_partial

    blocker = threading.Event()
    receipt: list[dict] = []

    def slow_ats(*, partial_sink, max_results, **_kwargs):
        rows = [
            {"title": "Data Engineer", "company": "Seed Co", "url": "https://seed.example/1", "source": "slow_ats"},
            {"title": "Data Engineer", "company": "Watched Co", "url": "https://watched.example/1", "source": "slow_ats", PROTECTED_ROW_KEY: True},
        ]
        publish_partial(partial_sink, rows)
        # The scraper's own cap strips the protection flag from the very dicts
        # the sink holds, then the thread hangs past the deadline.
        cap_with_protected(rows, ["Data Engineer"], max_results)
        blocker.wait(10)
        return []

    registry = {
        "slow_ats": ScraperMeta(name="slow_ats", display_name="Slow ATS", url="https://slow.example", description="", category="ats", enabled_by_default=True, search_fn=slow_ats),
    }
    from job_finder.models import database as database_module

    try:
        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(registry_module, "_SCRAPER_POOL_TIMEOUT_SECONDS", 0.3), \
             patch.object(database_module, "record_scrape_runs", lambda _rows: None):
            jobs = run_scrapers(names=["slow_ats"], roles=["Data Engineer"], max_results=1, outcome_sink=receipt)
    finally:
        blocker.set()

    urls = {job["url"] for job in jobs}
    assert "https://watched.example/1" in urls, "the watched company's row must survive the cap"
    assert receipt[0]["finish_reason"] == "partial"


# ── 3. partial outcomes reach the receipt honestly ──────────────────────────

def test_coverage_receipt_keeps_a_partial_source_partial() -> None:
    entry = _source_coverage_entry(
        "greenhouse",
        "Greenhouse",
        [{"finish_reason": "partial", "rows_found": 412, "error_sample": "deadline 100s hit; kept 412 rows fetched so far"}],
    )
    assert entry["state"] == "partial"
    assert "deadline" in entry["error"]


def test_coverage_receipt_treats_a_partial_source_with_no_rows_as_failed() -> None:
    entry = _source_coverage_entry(
        "lever",
        "Lever",
        [{"finish_reason": "partial", "rows_found": 0, "error_sample": "deadline 100s hit; kept 0 rows fetched so far"}],
    )
    assert entry["state"] == "failed"


# ── 4. a harvested source does not settle twice ─────────────────────────────

def test_a_harvested_source_that_finishes_late_is_settled_once() -> None:
    from job_finder import row_contract

    release = threading.Event()
    finished = threading.Event()
    settle_calls: list[str] = []
    real_validate = row_contract.validate_rows

    def counting_validate(jobs, meta):
        settle_calls.append(meta.name)
        return real_validate(jobs, meta)

    def slow(*, partial_sink, **_kwargs):
        partial_sink.append({"title": "Data Engineer", "company": "Acme", "url": "https://acme.example/1", "source": "slow"})
        release.wait(10)
        finished.set()
        return [{"title": "Data Engineer", "company": "Acme", "url": "https://acme.example/1", "source": "slow"}]

    registry = {
        "slow": ScraperMeta(name="slow", display_name="Slow", url="https://slow.example", description="", category="ats", enabled_by_default=True, search_fn=slow),
    }
    from job_finder.models import database as database_module

    with patch.dict(registry_module._REGISTRY, registry, clear=True), \
         patch.object(registry_module, "_SCRAPER_POOL_TIMEOUT_SECONDS", 0.2), \
         patch.object(row_contract, "validate_rows", counting_validate), \
         patch.object(database_module, "record_scrape_runs", lambda _rows: None):
        jobs = run_scrapers(names=["slow"], roles=["Data Engineer"])
        assert len(jobs) == 1
        harvested_settles = len(settle_calls)
        release.set()
        assert finished.wait(5)
        # Give the late thread a moment to (wrongly) settle again.
        threading.Event().wait(0.3)

    assert harvested_settles == 1
    assert len(settle_calls) == 1, f"late finish settled again: {settle_calls}"
