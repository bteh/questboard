"""A board's volume cap in one place must not cancel its queries in another.

Real case (Brian, Sep 9 2026): 16 terms across ["Los Angeles, CA", "Remote"]
on Indeed and LinkedIn. The Los Angeles queries alone pushed each board past
``max_unique_jobs``, so both boards declared "coverage complete" after 3 of
16 Remote queries. The location filter then dropped 70% of the Los Angeles
rows as onsite-elsewhere, and the Remote side (where a remote-friendly
search actually lives) was never asked.

Rule under test: the volume budget is per board PER PLACE. Filling the
first place's budget stops further work in that place only; every saved
role is still queried once in every later place.
"""

from __future__ import annotations

from job_finder.pipeline import JobFinderPipeline

ROLES = [
    "Data Engineering Manager",
    "Data Platform Manager",
    "Analytics Engineering Manager",
]


def _config(max_unique: int) -> dict:
    return {
        "job_boards": ["indeed"],
        "additional_sources": [],
        "search_settings": {
            "ai_expand_roles": False,
            "max_parallel_searches": 1,
            "max_search_tasks": 12,
            "max_unique_jobs": max_unique,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }


def _install_fakes(monkeypatch, calls: list[tuple[str, bool]]) -> None:
    def fake_search_jobs(*, search_term, location, is_remote, telemetry, **_kwargs):
        calls.append((search_term, bool(is_remote)))
        jobs = [
            {
                "title": search_term.title(),
                "company": f"Co {i}",
                "location": "Remote" if is_remote else location,
                "url": f"https://indeed.example/{search_term}/{is_remote}/{i}",
                "source": "indeed",
                "description": "Lead the data platform.",
                "is_remote": bool(is_remote),
            }
            for i in range(100)
        ]
        telemetry.update({
            "finish_reason": "ok",
            "rows_found": len(jobs),
            "duration_s": 0.01,
            "error_sample": "",
        })
        return jobs

    import job_finder.models.database as database_module
    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(database_module, "record_scrape_runs", lambda _rows: None)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])


def test_first_place_filling_the_cap_still_queries_every_role_in_the_second_place(
    monkeypatch,
) -> None:
    calls: list[tuple[str, bool]] = []
    _install_fakes(monkeypatch, calls)

    pipeline = JobFinderPipeline(llm=None)
    # 100 rows per query: the first Los Angeles query alone fills this cap.
    pipeline.config = _config(max_unique=100)

    pipeline.search_all_jobs(roles=ROLES, locations=["Los Angeles, CA", "Remote"])

    expected = {"data engineering manager", "data platform manager", "analytics engineering manager"}
    la_terms = {term for term, is_remote in calls if not is_remote}
    remote_terms = {term for term, is_remote in calls if is_remote}
    assert la_terms == expected
    assert remote_terms == expected


def test_cap_still_stops_extra_queries_inside_a_place(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []
    _install_fakes(monkeypatch, calls)

    pipeline = JobFinderPipeline(llm=None)
    config = _config(max_unique=100)
    # One query per place satisfies the minimum, so the cap may stop the rest.
    config["search_settings"]["min_queries_per_source"] = 1
    pipeline.config = config

    pipeline.search_all_jobs(roles=ROLES, locations=["Los Angeles, CA", "Remote"])

    la_calls = [term for term, is_remote in calls if not is_remote]
    remote_calls = [term for term, is_remote in calls if is_remote]
    assert len(la_calls) == 1
    assert len(remote_calls) == 1
