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
    "text, expected_min, expected_max, expected_period",
    [
        # k-suffixed range with dollars
        ("Compensation: $140k-$170k plus equity", 140000.0, 170000.0, "annual"),
        ("$140K - $170K", 140000.0, 170000.0, "annual"),
        # full dollar amounts with 'to'
        ("The base salary is $140,000 to $170,000 annually.", 140000.0, 170000.0, "annual"),
        # bare k-range, k only on the upper bound
        ("Salary: 140-170k depending on experience", 140000.0, 170000.0, "annual"),
        # between ... and ...
        ("between $120,000 and $150,000", 120000.0, 150000.0, "annual"),
        # hourly single -> RAW rate with period marker (never annualized here)
        ("$45/hr", 45.0, None, "hourly"),
        ("Pays $45 per hour.", 45.0, None, "hourly"),
        # hourly range -> raw both ends
        ("Pay range: $40 - $50 per hour", 40.0, 50.0, "hourly"),
        # up to -> max only
        ("earn up to $170,000", None, 170000.0, "annual"),
        ("up to $170k for senior candidates", None, 170000.0, "annual"),
        # single annual figure with an annual anchor after it -> min only
        ("This role pays $130,000/year", 130000.0, None, "annual"),
        ("$180k per annum", 180000.0, None, "annual"),
        ("Base is $150,000 annually", 150000.0, None, "annual"),
        # single annual figure introduced by a salary/comp preamble -> min only
        ("The base salary range for this position is $180,000", 180000.0, None, "annual"),
        ("Compensation: $200,000", 200000.0, None, "annual"),
        # 'USD'/'US$' ISO forms let a symbol-less range parse
        ("USD 140,000 - 180,000 per year", 140000.0, 180000.0, "annual"),
        ("US$130,000/year", 130000.0, None, "annual"),
        # a stated range still wins over the single-value reading
        ("$272,000 to $306,000 + equity", 272000.0, 306000.0, "annual"),
        # ── negative cases: numbers that are NOT salaries ────────────────
        # sub-floor fees/stipends stay unparsed even with a comp label
        ("Compensation: $250", None, None, None),
        ("Salary: $700 signing bonus", None, None, None),
        # a bare number with no currency symbol and no ISO code never parses
        ("Salary: 90,000 - 120,000 per year", None, None, None),
        ("This role pays 130,000/year", None, None, None),
        # a 401k retirement match near a 'salary' word is not a $401,000 salary
        ("Competitive Base Salary plus Pre-IPO Equity 401k Matching up to 4%", None, None, None),
        ("Base Salary and 401k matching", None, None, None),
        # a bare 401k figure a 'salary' word precedes, past a comma/word/period
        ("Competitive salary, 401k, and health insurance", None, None, None),
        ("We offer a great salary and 401k plan", None, None, None),
        ("Competitive base salary plus 401k.", None, None, None),
        # a single figure that is explicitly a bonus/stipend, not base pay
        ("Competitive salary and a $30,000 annual bonus", None, None, None),
        ("Base salary plus a $25,000 relocation stipend", None, None, None),
        # company money stated as "$X per year", not pay
        ("We are generating $250,000 per year", None, None, None),
        ("Our platform processes $500,000 per year in fees", None, None, None),
        # a range whose lead noun marks it as a bonus/equity/budget/ARR, not base pay
        ("The annual bonus is $30k-$40k.", None, None, None),
        ("Equity grant value: $100k-$150k.", None, None, None),
        ("Our annual marketing budget is $140k-$170k.", None, None, None),
        ("ARR was $140k-$170k.", None, None, None),
        ("401(k) contribution is $25k-$30k per year.", None, None, None),
        # a single base salary followed by a SEPARATE bonus/equity item still parses
        ("Base salary is $150,000 per year plus a bonus.", 150000.0, None, "annual"),
        ("Base salary is $150,000 per year plus an equity grant.", 150000.0, None, "annual"),
        ("5 years experience required", None, None, None),
        ("401k matching and great benefits", None, None, None),
        ("401(k) with company match", None, None, None),
        ("join a team of 150 engineers", None, None, None),
        ("3-5 years of Python experience", None, None, None),
        ("up to 20% annual bonus", None, None, None),
        ("we raised $5M in funding", None, None, None),
        ("serving 100-150k users", None, None, None),
        ("", None, None, None),
        (None, None, None, None),
        # ── company money, not pay: budgets / revenue / funding ──────────
        ("You will own a $140,000 to $170,000 cloud infrastructure budget.", None, None, None),
        ("We manage a $140k-$170k marketing budget", None, None, None),
        ("reach $25k-$50k MRR by Q4", None, None, None),
        ("grow from $300k to $900k ARR", None, None, None),
        ("raised a $140k-$170k pre-seed", None, None, None),
        ("we raised $500k to $700k in funding", None, None, None),
        ("closing a $140k-$170k seed round", None, None, None),
        ("processing $25k-$50k in transactions daily", None, None, None),
        ("a $1,200,000-$1,800,000 valuation", None, None, None),
        ("scale revenue up to $170k", None, None, None),
    ],
)
def test_extract_salary_range(text, expected_min, expected_max, expected_period):
    result = extract_salary_range(text)
    assert (result.salary_min, result.salary_max, result.period) == (
        expected_min, expected_max, expected_period,
    )


@pytest.mark.parametrize(
    "text, expected_min, expected_max",
    [
        # Sentence/clause boundaries protect real salaries near budget talk.
        ("Salary: $140k-$170k. You will manage the marketing budget.", 140000.0, 170000.0),
        ("Compensation: $140k-$170k, equity, and a generous learning budget", 140000.0, 170000.0),
        # 'budget'/'raised' before the amount but not as funding context.
        ("Our budget for this role is $140,000 to $170,000.", 140000.0, 170000.0),
        ("We recently raised our salary bands to $140,000 to $170,000.", 140000.0, 170000.0),
    ],
)
def test_extract_salary_range_keeps_real_salaries_near_company_money_words(
    text, expected_min, expected_max
):
    result = extract_salary_range(text)
    assert (result.salary_min, result.salary_max) == (expected_min, expected_max)


def test_finalize_does_not_stamp_salary_from_budget_figures():
    """End-to-end: a budget range must not become salary_source='parsed_from_description'."""
    job = {
        "title": "Platform Engineer",
        "description": "You will own a $140,000 to $170,000 cloud infrastructure budget.",
        "salary_min": None,
        "salary_max": None,
    }
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_min"] is None
    assert out["salary_max"] is None
    assert out["salary_source"] is None


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


def test_iso_form_maps_currency_to_usd():
    """The symbol-less 'USD' anchor still records the currency as USD."""
    result = extract_salary_range("USD 140,000 - 180,000 per year")
    assert result.currency == "USD"


def test_finalize_parses_single_annual_figure():
    """A greenhouse-style single stated figure fills salary_min, not 'not stated'."""
    job = {
        "title": "Data Engineer",
        "description": "The base salary range for this position is $180,000.",
        "salary_min": None,
        "salary_max": None,
    }
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_min"] == 180000.0
    assert out["salary_max"] is None
    assert out["salary_source"] == "parsed_from_description"
