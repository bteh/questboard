"""Contract tests for the EdJoin career scraper.

Fixture: 12 REAL rows from www.edjoin.org/Home/LoadJobs, captured live
2026-10-08 (HTTP 200) from the "analyst", "support specialist",
"information technology", and "technician" searches. They cover each pay
box shape (Pay Range, Single Rate, Dependent with prose), step and range
labels inside the pay box, four internal-only postings, and one
out-of-state row. No live HTTP inside tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from job_finder.tools.scrapers import edjoin
from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "edjoin_loadjobs.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _by_title(rows: list[dict]) -> dict[str, dict]:
    return {r["title"]: r for r in rows}


def test_rows_carry_employer_city_url_and_date() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    burbank = rows["INFORMATION TECHNOLOGY SYSTEMS ANALYST"]
    assert burbank["company"] == "Burbank Unified"
    assert burbank["location"] == "Burbank, CA"
    assert burbank["url"] == "https://www.edjoin.org/Home/JobPosting/2280957"
    assert burbank["source"] == "edjoin"
    assert burbank["date_posted"].startswith("2026-09-30")
    assert burbank["date_confidence"] == "exact"
    assert burbank["job_type"] == "fulltime"
    assert burbank["is_remote"] is False


def test_pay_range_box_is_stated_pay() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    burbank = rows["INFORMATION TECHNOLOGY SYSTEMS ANALYST"]
    assert (burbank["salary_min"], burbank["salary_max"]) == (6895.0, 8822.0)
    assert burbank["salary_period"] == "monthly"
    assert burbank["salary_currency"] == "USD"


def test_single_rate_box_is_a_point_value() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    brea = rows["CALPADS/SIS DATA ANALYST - SHORT TERM"]
    assert brea["company"] == "Brea Olinda Unified School District"
    assert (brea["salary_min"], brea["salary_max"], brea["salary_period"]) == (
        5151.0, 5151.0, "monthly",
    )


def test_step_labels_in_pay_box_are_not_money() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    pasadena = rows["Facilities Technician (Bond Projects)"]
    assert (pasadena["salary_min"], pasadena["salary_max"]) == (6586.0, 7705.0)
    lbusd = rows["HVAC Technician"]
    assert (lbusd["salary_min"], lbusd["salary_max"], lbusd["salary_period"]) == (
        39.41, 48.83, "hourly",
    )


def test_dependent_pay_leaves_salary_empty_but_keeps_the_stated_text() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    lacoe = rows["Information Technology Trainee - Eligibility Pool"]
    assert lacoe["salary_min"] is None and lacoe["salary_max"] is None
    assert "$18.86 Hourly" in lacoe["description"]


def test_internal_only_postings_drop() -> None:
    titles = {r["title"] for r in edjoin.parse_results(_payload(), None)}
    assert not any("Current Employees" in t for t in titles)
    assert not any("EMPLOYEES ONLY" in t for t in titles)
    assert not any("limited to Classified" in t for t in titles)
    assert "Specialist III: Tech Support (Outside Candidates)" in titles
    assert len(titles) == 8


def test_out_of_state_row_keeps_its_own_state() -> None:
    rows = _by_title(edjoin.parse_results(_payload(), None))
    assert rows["Analyst-Grants"]["location"] == "Baltimore, MD"


def test_role_filter_applies() -> None:
    titles = [r["title"] for r in edjoin.parse_results(_payload(), ["Data Analyst"])]
    assert titles == ["CALPADS/SIS DATA ANALYST - SHORT TERM"]


def test_search_terms_add_each_roles_last_word_once() -> None:
    assert edjoin.search_terms(["IT Support Specialist", "Data Analyst", "Business Analyst"]) == [
        "IT Support Specialist", "Data Analyst", "Business Analyst", "specialist", "analyst",
    ]


def test_search_pages_dedupes_and_publishes_partials() -> None:
    payload = _payload()
    payload["totalPages"] = 2
    calls: list[dict] = []

    def fake_get_json(url, params=None, **kwargs):
        calls.append(dict(params))
        return payload

    sink: list[dict] = []
    with patch.object(edjoin, "_get_json", side_effect=fake_get_json):
        rows = edjoin.search_edjoin(
            roles=["Analyst"], locations=["El Monte, CA"], partial_sink=sink,
        )
    assert [c["page"] for c in calls] == [1, 2]
    assert {c["keywords"] for c in calls} == {"Analyst"}
    urls = [r["url"] for r in rows]
    assert len(urls) == len(set(urls))
    assert {r["url"] for r in sink} == set(urls)


def test_no_fetch_without_a_california_place() -> None:
    with patch.object(edjoin, "_get_json") as fetch:
        assert edjoin.search_edjoin(roles=["Data Analyst"], locations=["Austin, TX"]) == []
    fetch.assert_not_called()


def test_registered_as_a_default_career_source() -> None:
    meta = get_registry()["edjoin"]
    assert meta.vertical == "career"
    assert meta.category == "public"
    assert meta.allowed_url_hosts == ("edjoin.org",)
    assert "edjoin" in default_scraper_names()
