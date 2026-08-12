from __future__ import annotations

from unittest.mock import patch

from job_finder.tools.scrapers import getro_startups as mod


def _raw_job(title: str, company: str, url: str) -> dict:
    return {
        "title": title,
        "organization": {"name": company, "head_count": 12, "stage": "seed"},
        "url": url,
        "work_mode": "remote",
        "locations": ["United States"],
        "seniority": "senior",
        "skills": ["SQL", "dbt"],
        "created_at": "2026-08-01T00:00:00Z",
    }


def test_search_queries_adds_founding_family_and_deduplicates_levels() -> None:
    assert mod._search_queries(
        [
            "Staff Data Engineer",
            "Director, Data Engineering",
            "Data Engineering Manager",
            "Analytics Engineering Manager",
        ]
    ) == [
        "founding data engineer",
        "founding analytics engineer",
        "data engineer",
        "analytics engineer",
    ]


def test_scraper_keeps_matching_founding_role_and_rejects_other_profession() -> None:
    page = [
        _raw_job(
            "Founding Data Engineer (Pipelines)",
            "Seed Data Co",
            "https://portfolio.example/jobs/data",
        ),
        _raw_job(
            "Founding Software Engineer",
            "Seed Software Co",
            "https://portfolio.example/jobs/software",
        ),
    ]
    with patch.object(mod, "_fetch_search", return_value=page) as fetch:
        jobs = mod.search_getro_startups(
            roles=["Staff Data Engineer"],
            max_results=20,
        )

    assert [(job["title"], job["source"]) for job in jobs] == [
        ("Founding Data Engineer (Pipelines)", "getro_startups"),
    ]
    assert fetch.call_args.kwargs["query"] == "data engineer"


def test_scraper_stops_on_a_short_page() -> None:
    with patch.object(
        mod,
        "_fetch_search",
        return_value=[
            _raw_job(
                "Data Engineering Manager",
                "Portfolio Co",
                "https://portfolio.example/jobs/manager",
            )
        ],
    ) as fetch:
        jobs = mod.search_getro_startups(
            roles=["Data Engineering Manager"],
            max_results=20,
        )

    assert len(jobs) == 1
    # One short page per network for the founding query and its base query.
    assert fetch.call_count == 4
