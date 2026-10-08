"""Contract tests for the CSU Careers (PageUp RSS) scraper.

Fixture: the real channel header plus 6 REAL items from
careers.pageuppeople.com/873/cw/en-us/rss, captured live 2026-10-08
(HTTP 200, 2,568 items): Cal Poly Pomona Administrative Analyst
(anticipated hiring range), Cal State Fullerton Technology Support
Specialist I (not-anticipated-to-exceed range), a Cal Poly Pomona
executive role (annual range), a faculty posting (unlabelled annual range
plus an H-1B fee figure), a student-assistant job, and a Cal State LA
Fiscal Analyst. No live HTTP inside tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from job_finder.tools.scrapers import csu_careers
from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "csu_careers_rss.xml"


def _feed() -> bytes:
    return FIXTURE.read_bytes()


def _by_title(rows: list[dict]) -> dict[str, dict]:
    return {r["title"]: r for r in rows}


def test_campus_label_maps_to_employer_and_city() -> None:
    rows = _by_title(csu_careers.parse_feed(_feed(), None))
    pomona = rows["Administrative Analyst"]
    assert pomona["company"] == "Cal Poly Pomona"
    assert pomona["location"] == "Pomona, CA"
    assert rows["Technology Support Specialist I"]["company"] == "Cal State Fullerton"
    assert rows["Fiscal Analyst"]["company"] == "Cal State LA"
    assert rows["Fiscal Analyst"]["location"] == "Los Angeles, CA"


def test_rows_carry_posting_url_date_and_text() -> None:
    row = _by_title(csu_careers.parse_feed(_feed(), None))["Administrative Analyst"]
    assert row["url"] == "https://careers.pageuppeople.com/873/cw/en-us/job/562857"
    assert row["source"] == "csu_careers"
    assert row["date_posted"] == "2026-10-08T16:00:00"
    assert row["date_confidence"] == "exact"
    assert row["job_type"] == "fulltime"
    assert "Anticipated Hiring Range" in row["description"]
    assert "<" not in row["description"]


def test_hiring_range_is_the_stated_pay() -> None:
    rows = _by_title(csu_careers.parse_feed(_feed(), None))
    pomona = rows["Administrative Analyst"]
    assert (pomona["salary_min"], pomona["salary_max"], pomona["salary_period"]) == (
        5274.0, 5597.0, "monthly",
    )
    assert pomona["salary_currency"] == "USD"
    fullerton = rows["Technology Support Specialist I"]
    assert (fullerton["salary_min"], fullerton["salary_max"]) == (4595.0, 4974.0)


def test_annual_ranges_and_the_h1b_fee() -> None:
    rows = _by_title(csu_careers.parse_feed(_feed(), None))
    exec_row = next(r for t, r in rows.items() if t.startswith("Executive Director"))
    assert (exec_row["salary_min"], exec_row["salary_max"], exec_row["salary_period"]) == (
        125000.0, 142000.0, "annual",
    )
    faculty = next(r for t, r in rows.items() if t.startswith("Geological Sciences"))
    assert (faculty["salary_min"], faculty["salary_max"]) == (90812.0, 94812.0)


def test_student_assistant_jobs_drop() -> None:
    titles = {r["title"] for r in csu_careers.parse_feed(_feed(), None)}
    assert not any("Student Assistant" in t for t in titles)
    assert len(titles) == 5


def test_role_filter_applies() -> None:
    titles = [r["title"] for r in csu_careers.parse_feed(_feed(), ["Fiscal Analyst"])]
    assert titles == ["Fiscal Analyst"]


def test_unmapped_campus_falls_back_to_the_system() -> None:
    assert csu_careers.campus_for("Southern California|Nowhere Campus") == (
        "California State University", "California",
    )
    assert csu_careers.campus_for(
        "Southern California|San Diego - Imperial Valley,Southern California|San Diego"
    ) == ("San Diego State University", "Calexico, CA")


def test_broken_feed_returns_nothing() -> None:
    assert csu_careers.parse_feed(b"<html>maintenance</html", None) == []


def test_search_fetches_once_and_caps() -> None:
    with patch.object(csu_careers, "_fetch_feed", return_value=_feed()) as fetch:
        rows = csu_careers.search_csu_careers(
            roles=["Analyst"], max_results=1, locations=["Pomona, CA"],
        )
    fetch.assert_called_once()
    assert len(rows) == 1


def test_no_fetch_without_a_california_place() -> None:
    with patch.object(csu_careers, "_fetch_feed") as fetch:
        assert csu_careers.search_csu_careers(roles=["Analyst"], locations=["Remote"]) == []
    fetch.assert_not_called()


def test_registered_as_a_default_career_source() -> None:
    meta = get_registry()["csu_careers"]
    assert meta.vertical == "career"
    assert meta.category == "public"
    assert "csu_careers" in default_scraper_names()
