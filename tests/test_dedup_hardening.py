"""Dedup hardening: URL canonicalization + thin-description fallback.

Cross-source duplicates survived dedup in two ways:
1. The phase-1 URL grouping compared raw URLs, so tracking-param variants
   (utm_*, ref, gh_src) and Greenhouse/Lever URL-shape variants of the SAME
   posting never grouped.
2. LinkedIn rows often arrive description-less, so description matching
   couldn't confirm the duplicate (covered by the company+title+location
   compatibility fallback in ``_same_posting``).
"""

from __future__ import annotations

import pytest

from job_finder.pipeline import _deduplicate
from job_finder.tools.scrapers._utils import canonicalize_job_url

_DESC_A = (
    "Own and scale the data platform end to end: design batch and streaming "
    "pipelines, lead the lakehouse migration, and mentor two engineers on it."
)
_DESC_B = (
    "Build the consumer-facing React dashboard, own the design-system "
    "components, and partner with product on the onboarding redesign work."
)


def _job(title, company, loc, desc, url, remote=False, **extra):
    return {
        "title": title, "company": company, "location": loc,
        "description": desc, "url": url, "is_remote": remote, **extra,
    }


# ── canonicalize_job_url ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("left", "right"),
    [
        (  # tracking params stripped
            "https://example.com/jobs/123?utm_source=news&utm_medium=email&ref=home",
            "https://example.com/jobs/123",
        ),
        (  # gh_src + greenhouse host variants → stable job id
            "https://boards.greenhouse.io/acme/jobs/4012345?gh_src=abc123",
            "https://job-boards.greenhouse.io/acme/jobs/4012345",
        ),
        (  # greenhouse embed form → same stable job id
            "https://boards.greenhouse.io/embed/job_app?for=acme&token=4012345",
            "https://boards.greenhouse.io/acme/jobs/4012345",
        ),
        (  # lever /apply suffix + tracking param
            "https://jobs.lever.co/acme/9f8a7b6c-1d2e-3f4a-5b6c-7d8e9f0a1b2c/apply?lever-source=LinkedIn",
            "https://jobs.lever.co/acme/9f8a7b6c-1d2e-3f4a-5b6c-7d8e9f0a1b2c",
        ),
        (  # host case + trailing slash + fragment
            "HTTPS://Example.com/careers/role/?utm_campaign=x#apply",
            "https://example.com/careers/role",
        ),
    ],
)
def test_url_variants_share_canonical_key(left: str, right: str) -> None:
    assert canonicalize_job_url(left) == canonicalize_job_url(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (  # different greenhouse job ids stay distinct
            "https://boards.greenhouse.io/acme/jobs/111",
            "https://boards.greenhouse.io/acme/jobs/222",
        ),
        (  # different companies stay distinct
            "https://boards.greenhouse.io/acme/jobs/111",
            "https://boards.greenhouse.io/globex/jobs/111",
        ),
        (  # meaningful (non-tracking) params are preserved
            "https://example.com/careers?gh_jid=111",
            "https://example.com/careers?gh_jid=222",
        ),
    ],
)
def test_distinct_jobs_keep_distinct_keys(left: str, right: str) -> None:
    assert canonicalize_job_url(left) != canonicalize_job_url(right)


def test_canonicalize_handles_garbage_gracefully() -> None:
    assert canonicalize_job_url("") == ""
    assert canonicalize_job_url(None) == ""
    assert canonicalize_job_url("not a url") != ""  # never raises


# ── _deduplicate integration ─────────────────────────────────────────────────

def test_tracking_param_variants_merge_in_phase1() -> None:
    # Substantial but DIFFERENT descriptions would survive the phase-2
    # description check — only canonical URL grouping can merge these.
    jobs = [
        _job("Data Engineer", "Acme", "Remote", _DESC_A,
             "https://example.com/jobs/123?utm_source=linkedin&ref=feed", remote=True),
        _job("Data Engineer", "Acme", "Remote", _DESC_B,
             "https://example.com/jobs/123", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 1


def test_greenhouse_id_variants_merge_in_phase1() -> None:
    jobs = [
        _job("Platform Engineer", "Acme", "Remote", _DESC_A,
             "https://boards.greenhouse.io/acme/jobs/4012345?gh_src=tok", remote=True),
        _job("Platform Engineer", "Acme", "Remote", _DESC_B,
             "https://job-boards.greenhouse.io/acme/jobs/4012345", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 1


def test_same_company_title_location_one_empty_description_merges() -> None:
    # The LinkedIn case: identical posting, but one side has no description.
    jobs = [
        _job("Senior Data Engineer", "Acme", "Austin, TX", _DESC_A, "u1"),
        _job("Senior Data Engineer", "Acme", "Austin, TX", "", "u2"),
    ]
    assert len(_deduplicate(jobs)) == 1


def test_different_concrete_locations_still_distinct() -> None:
    jobs = [
        _job("Senior Data Engineer", "Acme", "Austin, TX", _DESC_A, "u1"),
        _job("Senior Data Engineer", "Acme", "Seattle, WA", "", "u2"),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_merged_keeper_borrows_salary_and_provenance() -> None:
    jobs = [
        _job("Data Engineer", "Acme", "Remote", _DESC_A,
             "https://example.com/jobs/123?utm_source=x", remote=True),
        _job("Data Engineer", "Acme", "Remote", "",
             "https://example.com/jobs/123", remote=True,
             salary_min=60000.0, salary_max=70000.0,
             salary_source="parsed_from_description"),
    ]
    merged = _deduplicate(jobs)
    assert len(merged) == 1
    keeper = merged[0]
    assert keeper["salary_min"] == 60000.0
    assert keeper["salary_source"] == "parsed_from_description"
