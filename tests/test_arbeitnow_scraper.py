"""Regression tests for the Arbeitnow scraper.

2026-07-21 audit: the live run finished with reason "exception" and 0 rows.
Root cause: ``_parse_salary``'s number pattern ``[\\d,]+`` also matches a bare
comma, so the first matched job whose description contained commas (that is,
nearly any English prose) produced ``float('')`` -> ValueError and killed the
whole scraper run.

These tests pin three things:
1. ``_parse_salary`` never crashes on comma-bearing prose.
2. ``_parse_salary`` still parses real salary strings (remotive and the YC
   scraper feed it dedicated salary fields).
3. ``search_arbeitnow`` returns rows and does not fabricate pay from prose
   numbers ("5 years", "Python 3"). Description salary parsing is left to
   the conservative ``extract_salary_range`` in ``finalize_scraper_jobs``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._utils import _parse_salary  # noqa: E402
from job_finder.tools.scrapers.arbeitnow import search_arbeitnow  # noqa: E402


def _payload(description: str) -> dict:
    return {
        "data": [
            {
                "title": "Staff Data Engineer",
                "company_name": "Acme GmbH",
                "location": "Berlin",
                "url": "https://www.arbeitnow.com/jobs/acme/staff-data-engineer-123",
                "description": description,
                "tags": ["Data"],
                "remote": True,
                "created_at": 1752940800,
            },
        ],
        "links": {"next": None},
    }


def test_parse_salary_survives_bare_commas():
    # ``[\d,]+`` used to match a lone comma; float('') then raised ValueError.
    assert _parse_salary("We are hiring, come join us, thanks") == (None, None)


def test_parse_salary_survives_comma_only_salary_field():
    # Remotive-style free-text salary field with no digits at all.
    assert _parse_salary("Competitive, plus equity") == (None, None)


def test_parse_salary_still_parses_real_ranges():
    assert _parse_salary("$120,000 - $180,000") == (120000.0, 180000.0)
    assert _parse_salary("$120k - $180k") == (120000.0, 180000.0)


def test_arbeitnow_returns_rows_for_comma_descriptions():
    payload = _payload(
        "<p>We build pipelines, lakes, and warehouses. Join us, remote friendly.</p>"
    )
    with patch(
        "job_finder.tools.scrapers.arbeitnow._get_json", return_value=payload
    ):
        jobs = search_arbeitnow(
            roles=["Data Engineering Manager", "Staff Data Engineer"],
            max_results=10,
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Staff Data Engineer"
    assert jobs[0]["source"] == "arbeitnow"


def test_arbeitnow_does_not_fabricate_salary_from_prose_numbers():
    # "5 years" / "Python 3" must never become salary_min/salary_max.
    payload = _payload(
        "<p>5+ years of experience with Python 3 and Spark. 401(k) plan.</p>"
    )
    with patch(
        "job_finder.tools.scrapers.arbeitnow._get_json", return_value=payload
    ):
        jobs = search_arbeitnow(roles=["Staff Data Engineer"], max_results=10)
    assert len(jobs) == 1
    assert jobs[0]["salary_min"] is None
    assert jobs[0]["salary_max"] is None
