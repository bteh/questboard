"""Deterministic salary extraction from job descriptions.

Greenhouse/Lever report no structured salary for most jobs, which made the
pipeline's salary filter a no-op. ``extract_salary_range`` in scrapers
``_utils`` parses common phrasings from description text; the shared
post-processing applies it to any scraper job that lacks reported salary
and stamps ``salary_source`` per the shared contract
('reported' | 'parsed_from_description' | None).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._utils import (  # noqa: E402
    extract_salary_range,
    finalize_scraper_jobs,
)


@pytest.mark.parametrize(
    "text, expected_min, expected_max",
    [
        # k-suffixed range with dollars
        ("Compensation: $140k-$170k plus equity", 140000.0, 170000.0),
        ("$140K - $170K", 140000.0, 170000.0),
        # full dollar amounts with 'to'
        ("The base salary is $140,000 to $170,000 annually.", 140000.0, 170000.0),
        # bare k-range, k only on the upper bound
        ("Salary: 140-170k depending on experience", 140000.0, 170000.0),
        # between ... and ...
        ("between $120,000 and $150,000", 120000.0, 150000.0),
        # hourly single -> annualized x2080
        ("$45/hr", 93600.0, None),
        ("Pays $45 per hour.", 93600.0, None),
        # hourly range -> annualized both ends
        ("Pay range: $40 - $50 per hour", 83200.0, 104000.0),
        # up to -> max only
        ("earn up to $170,000", None, 170000.0),
        ("up to $170k for senior candidates", None, 170000.0),
        # ── negative cases: numbers that are NOT salaries ────────────────
        ("5 years experience required", None, None),
        ("401k matching and great benefits", None, None),
        ("401(k) with company match", None, None),
        ("join a team of 150 engineers", None, None),
        ("3-5 years of Python experience", None, None),
        ("up to 20% annual bonus", None, None),
        ("we raised $5M in funding", None, None),
        ("serving 100-150k users", None, None),
        ("", None, None),
        (None, None, None),
    ],
)
def test_extract_salary_range(text, expected_min, expected_max):
    assert extract_salary_range(text) == (expected_min, expected_max)


# ── Shared post-processing applies the extractor + stamps salary_source ──────

def test_finalize_parses_salary_from_description():
    job = {
        "title": "Data Engineer",
        "description": "We offer a base salary of $140,000 to $170,000 plus equity.",
        "salary_min": None,
        "salary_max": None,
    }
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_min"] == 140000.0
    assert out["salary_max"] == 170000.0
    assert out["salary_source"] == "parsed_from_description"


def test_finalize_keeps_reported_salary():
    job = {
        "title": "Data Engineer",
        "description": "Pay is $90k-$100k.",  # must NOT override reported values
        "salary_min": 150000,
        "salary_max": 200000,
    }
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_min"] == 150000
    assert out["salary_max"] == 200000
    assert out["salary_source"] == "reported"


def test_finalize_no_salary_anywhere():
    job = {"title": "Data Engineer", "description": "Great team of 150 people."}
    out = finalize_scraper_jobs([job])[0]
    assert out.get("salary_min") is None
    assert out.get("salary_max") is None
    assert out["salary_source"] is None
