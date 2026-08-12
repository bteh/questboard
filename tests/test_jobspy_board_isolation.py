"""JobSpy boards must not block or discard one another's search results."""

from job_finder.pipeline import (
    JobFinderPipeline,
    _build_jobspy_tasks,
    _scaled_results_per_board,
    _source_coverage_entry,
    _source_coverage_receipt,
)


def test_query_consolidation_scales_result_volume_proportionally():
    assert _scaled_results_per_board(50, 18, 17) == 53
    assert _scaled_results_per_board(50, 20, 10) == 100
    assert _scaled_results_per_board(75, 100, 1) == 200


def test_source_receipt_distinguishes_partial_rows_from_total_failure():
    linkedin = _source_coverage_entry(
        "linkedin",
        "LinkedIn",
        [
            {"finish_reason": "ok", "rows_found": 53},
            {
                "finish_reason": "timeout",
                "rows_found": 0,
                "error_sample": "request exceeded 45s",
            },
        ],
    )
    workable = _source_coverage_entry(
        "workable",
        "Workable",
        [{"finish_reason": "timeout", "rows_found": 0}],
    )
    receipt = _source_coverage_receipt([linkedin, workable])

    assert linkedin["state"] == "partial"
    assert workable["state"] == "failed"
    assert receipt == {
        "total": 2,
        "ok": 0,
        "zero": 0,
        "partial": 1,
        "failed": 1,
        "sources": [linkedin, workable],
    }


def test_source_receipt_counts_a_clean_zero_as_a_completed_check():
    remoteok = _source_coverage_entry(
        "remoteok",
        "RemoteOK",
        [{"finish_reason": "zero_rows", "rows_found": 0}],
    )
    assert remoteok["state"] == "zero"
    assert remoteok["failed_attempts"] == 0


def test_explicit_boards_are_isolated_without_changing_query_coverage():
    combos = [
        ("data engineer", "Los Angeles, CA"),
        ("data engineer", "Remote"),
    ]

    tasks = _build_jobspy_tasks(combos, ["indeed", "linkedin"])

    assert tasks == [
        ("data engineer", "Los Angeles, CA", ["indeed"]),
        ("data engineer", "Los Angeles, CA", ["linkedin"]),
        ("data engineer", "Remote", ["indeed"]),
        ("data engineer", "Remote", ["linkedin"]),
    ]
    assert {
        (term, location, board)
        for term, location, only_board in tasks
        for board in only_board or []
    } == {
        (term, location, board)
        for term, location in combos
        for board in ("indeed", "linkedin")
    }


def test_default_boards_keep_legacy_grouped_behavior():
    assert _build_jobspy_tasks([("designer", "Remote")], None) == [
        ("designer", "Remote", None),
    ]


def test_explicit_empty_board_list_stays_disabled():
    assert _build_jobspy_tasks([("designer", "Remote")], []) == []


def test_pipeline_does_not_reenable_default_boards_for_explicit_empty_list(monkeypatch):
    def fail_search_jobs(**_kwargs):
        raise AssertionError("JobSpy must not run when job_boards is explicitly empty")

    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fail_search_jobs)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": [],
        "additional_sources": [],
        "search_settings": {
            "ai_expand_roles": False,
            "max_search_tasks": 12,
            "max_unique_jobs": 500,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }

    assert pipeline.search_all_jobs(
        roles=["Data Engineer"],
        locations=["Remote"],
    ) == []


def test_jobspy_uses_the_saved_jurisdiction_instead_of_us_defaults(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_search_jobs(*, location, country, telemetry, **_kwargs):
        calls.append((location, country))
        telemetry.update({"finish_reason": "zero_rows", "rows_found": 0})
        return []

    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": ["indeed"],
        "additional_sources": [],
        "search_settings": {
            "ai_expand_roles": False,
            "country": "United Kingdom",
            "country_by_location": {
                "london, united kingdom": "United Kingdom",
            },
            "max_parallel_searches": 1,
            "max_search_tasks": 12,
            "max_unique_jobs": 500,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }

    pipeline.search_all_jobs(
        roles=["Data Engineer"],
        locations=["London, United Kingdom", "Remote"],
    )

    assert calls == [
        ("London, United Kingdom", "United Kingdom"),
        ("United Kingdom", "United Kingdom"),
    ]


def test_one_board_failure_does_not_discard_another_boards_rows(monkeypatch):
    calls: list[str] = []

    def fake_search_jobs(*, boards, **_kwargs):
        board = boards[0]
        calls.append(board)
        if board == "linkedin":
            raise TimeoutError("simulated slow board")
        return [{
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Remote",
            "url": "https://jobs.example/indeed-data-engineer",
            "source": board,
            "description": "Build reliable data pipelines.",
            "is_remote": True,
        }]

    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": ["indeed", "linkedin"],
        "additional_sources": [],
        "search_settings": {
            "ai_expand_roles": False,
            "max_parallel_searches": 1,
            "max_search_tasks": 12,
            "max_unique_jobs": 500,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }

    jobs = pipeline.search_all_jobs(
        roles=["Data Engineer"],
        locations=["Remote"],
    )

    assert set(calls) == {"indeed", "linkedin"}
    assert [job["url"] for job in jobs] == [
        "https://jobs.example/indeed-data-engineer",
    ]
    coverage = pipeline._last_source_coverage
    by_source = {item["source"]: item for item in coverage["sources"]}
    assert by_source["indeed"]["state"] == "ok"
    assert by_source["linkedin"]["state"] == "failed"
    assert by_source["linkedin"]["attempts"] == 1
    assert by_source["linkedin"]["failed_attempts"] == 1
    assert "TimeoutError: simulated slow board" in by_source["linkedin"]["error"]


def test_prolific_board_cannot_starve_other_board_or_later_roles(monkeypatch):
    calls: list[tuple[str, str, str]] = []
    logged_runs: list[dict] = []

    def fake_search_jobs(*, boards, search_term, location, telemetry, **_kwargs):
        board = boards[0]
        calls.append((board, search_term, location))
        if board == "indeed":
            jobs = [
                {
                    "title": "Data Engineer",
                    "company": f"Indeed Co {i}",
                    "location": location,
                    "url": f"https://indeed.example/{search_term}/{location}/{i}",
                    "source": board,
                    "description": "Build data pipelines.",
                    "is_remote": location == "United States",
                }
                for i in range(100)
            ]
        else:
            jobs = [{
                "title": "Senior Manager, Analytics Engineering",
                "company": "FOX Tech",
                "location": "Los Angeles, CA",
                "url": f"https://linkedin.example/{search_term}/{location}",
                "source": board,
                "description": "Lead analytics engineering.",
                "is_remote": False,
            }]
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
    monkeypatch.setattr(database_module, "record_scrape_runs", logged_runs.extend)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": ["indeed", "linkedin"],
        "additional_sources": [],
        "search_settings": {
            "ai_expand_roles": False,
            "max_parallel_searches": 1,
            "max_search_tasks": 12,
            "max_unique_jobs": 100,
            "max_days_old": 30,
        },
        "location_preferences": {"include_remote": True},
    }
    roles = [
        "Staff Data Engineer",
        "Data Engineering Manager",
        "Senior Manager, Analytics Engineering",
    ]

    pipeline.search_all_jobs(
        roles=roles,
        locations=["Los Angeles, CA", "Remote"],
    )

    linkedin_calls = [call for call in calls if call[0] == "linkedin"]
    indeed_calls = [call for call in calls if call[0] == "indeed"]
    # Indeed hits the volume cap immediately, but still covers every role once.
    assert len(indeed_calls) >= len(roles)
    assert {term for _, term, _ in indeed_calls[:len(roles)]} == {
        "data engineer",
        "data engineering manager",
        "manager, analytics engineering",
    }
    # Indeed's cap cannot cancel a single LinkedIn query.
    assert len(linkedin_calls) == len(roles) * 2
    assert {run["source"] for run in logged_runs} == {"indeed", "linkedin"}
