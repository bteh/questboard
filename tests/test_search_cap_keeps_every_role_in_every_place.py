"""The query cap trims keyword searches, never a saved role in a chosen place.

Real case (Sep 15 2026): 18 saved roles and 4 title-shaped keyword phrases
across ["Los Angeles, CA", "Remote"] made 40 board queries; the hard cap of
30 kept the first 30 in place-major order and silently dropped the last
ten Remote queries, among them "analytics engineering manager", "analytics
engineering lead" and "manager, business intelligence". For a
remote-friendly search, those roles were never asked for remotely.

Rules under test:
1. Every saved role is queried in every chosen place, whatever the cap.
2. When the cap has to trim, keyword-derived terms lose their later-place
   queries first; roles are untouched.
3. The cap still bounds the run: the total never exceeds the larger of the
   cap and the number of role queries.
"""

from __future__ import annotations

from job_finder.pipeline import JobFinderPipeline

ROLES = [
    "Data Engineering Manager",
    "Analytics Engineering Manager",
    "Data Platform Manager",
    "Data Operations Manager",
    "Data Infrastructure Manager",
    "Data Governance Manager",
    "Analytics Engineering Lead",
    "Manager, Business Intelligence",
]
PHRASES = ["data platform", "data pipeline", "data products", "data engineering"]
PLACES = ["Los Angeles, CA", "Remote"]


def _run(monkeypatch, max_tasks: int) -> list[tuple[str, bool]]:
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

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": ["indeed"],
        "additional_sources": [],
        "target_roles": ROLES,
        "keyword_searches": PHRASES,
        "search_settings": {
            "ai_expand_roles": False,
            "max_parallel_searches": 1,
            "max_search_tasks": max_tasks,
            "max_unique_jobs": 100000,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }
    # The API path merges title-shaped keywords into the roles list.
    pipeline.search_all_jobs(roles=ROLES + PHRASES, locations=PLACES)
    return calls


def test_every_saved_role_runs_in_every_place_under_a_tight_cap(monkeypatch) -> None:
    calls = _run(monkeypatch, max_tasks=20)
    role_terms = {r.lower() for r in ROLES}
    for remote in (False, True):
        asked = {term for term, is_remote in calls if is_remote == remote}
        missing = role_terms - asked
        assert not missing, f"roles never queried ({'Remote' if remote else 'Los Angeles'}): {sorted(missing)}"


def test_the_cap_trims_keyword_phrases_before_roles(monkeypatch) -> None:
    calls = _run(monkeypatch, max_tasks=20)
    phrase_terms = {p.lower() for p in PHRASES}
    phrase_calls = [term for term, _ in calls if term in phrase_terms]
    # 8 roles x 2 places = 16 role queries; a cap of 20 leaves room for 4 phrase queries.
    assert len(phrase_calls) == 4
    assert len(calls) == 20


def test_the_cap_still_bounds_a_run_with_room_to_spare(monkeypatch) -> None:
    calls = _run(monkeypatch, max_tasks=30)
    # 8 roles + 4 phrases = 12 terms x 2 places = 24 queries, under the cap: nothing trimmed.
    assert len(calls) == 24
