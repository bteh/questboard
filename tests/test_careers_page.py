"""Every rule in scrapers/_careers_page.py, each pinned to the site behind it.

Fixtures are real pages fetched once on 2026-10-08 and trimmed to <head> plus
<main> (scripts other than JSON-LD, styles, and inline SVG icons removed):
elorea.com/pages/career-opportunities and elorea.com/pages/barista-la.
No live HTTP.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import _careers_page as pages  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
CAREERS_URL = "https://elorea.com/pages/career-opportunities"
BARISTA_URL = "https://elorea.com/pages/barista-la"


def _careers() -> str:
    return (FIXTURES / "elorea_careers.html").read_text(encoding="utf-8")


def _barista() -> str:
    return (FIXTURES / "elorea_barista_la.html").read_text(encoding="utf-8")


def test_elorea_smoothie_cards_read_every_opening():
    """ELOREA's Smoothie board on Shopify: six cards, each linking to its
    own /pages/<slug> detail page."""
    rows = pages.listing_rows(_careers(), CAREERS_URL)
    assert [r["title"] for r in rows] == [
        "Head of Finance",
        "Director of Operations",
        "Scent Advisor (Sales Associate) NY",
        "Scent Advisor (Sales Associate) LA",
        "Barista (NYC)",
        "Barista (LA)",
    ]
    by_title = {r["title"]: r for r in rows}
    barista = by_title["Barista (LA)"]
    assert barista["url"] == BARISTA_URL
    assert barista["location"] == "Koreatown, LA"
    assert barista["employment"] == "parttime"
    assert (barista["salary_min"], barista["salary_max"], barista["salary_period"]) == (
        22.0, 25.0, "hourly",
    )
    scent = by_title["Scent Advisor (Sales Associate) LA"]
    assert scent["url"] == "https://elorea.com/pages/brand-associate-retail-cx-la"
    assert (scent["salary_min"], scent["salary_max"]) == (20.0, 25.0)
    director = by_title["Director of Operations"]
    assert director["employment"] == "fulltime"
    assert "salary_min" not in director


def test_elorea_pay_text_reads_usd_per_hour():
    """ELOREA's Compensation span: "22 - 25 usd / hour"."""
    assert pages.parse_pay_text("22 - 25 usd / hour") == {
        "salary_min": 22.0, "salary_max": 25.0,
        "salary_period": "hourly", "salary_currency": "USD",
    }
    assert pages.parse_pay_text("Customer Relations") is None


def test_elorea_job_type_both_spellings():
    """ELOREA states the type as job-type="PART_TIME" and as "Part time"."""
    assert pages.employment_type("PART_TIME") == "parttime"
    assert pages.employment_type(" Part time ") == "parttime"
    assert pages.employment_type("FULL_TIME") == "fulltime"
    assert pages.employment_type(["FULL_TIME", "PART_TIME"]) == "parttime"
    assert pages.employment_type("") == ""


def test_elorea_detail_page_jobposting_jsonld():
    """ELOREA's detail page carries schema.org JobPosting with an HTML
    description escaped twice ("&lt;p&gt;")."""
    rows = pages.jobposting_rows(_barista(), BARISTA_URL)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Barista (LA)"
    assert row["company"] == "ELOREA"
    assert row["location"] == "Koreatown, LA"
    assert row["url"] == BARISTA_URL
    assert row["employment"] == "parttime"
    assert row["date_posted"] == "2024-10-28"
    assert (row["salary_min"], row["salary_max"], row["salary_period"]) == (22.0, 25.0, "hourly")
    assert row["description"].startswith("ELOREA is looking for a barista")
    assert "&lt;" not in row["description"] and "<p>" not in row["description"]


def test_listing_page_has_no_jobposting_so_read_page_falls_to_cards():
    assert pages.jobposting_rows(_careers(), CAREERS_URL) == []
    assert len(pages.read_page(_careers(), CAREERS_URL)) == 6


def test_elorea_shop_name_from_og_site_name():
    assert pages.shop_name(_careers(), CAREERS_URL) == "ELOREA"
    assert pages.shop_name("<html></html>", "https://www.bluebottlecoffee.com/x") == "Bluebottlecoffee"


def test_ats_board_links_are_detected():
    """Hosted boards the existing ATS fetchers read. Blue Bottle Coffee's
    board is jobs.lever.co/bluebottlecoffee (starter list, Oct 8 2026); the
    other shapes are the documented embed and board URLs for each host."""
    assert pages.find_ats_board("https://jobs.lever.co/bluebottlecoffee") == (
        "lever", "bluebottlecoffee",
    )
    embed = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=alfredcoffee"></script>'
    assert pages.find_ats_board(embed) == ("greenhouse", "alfredcoffee")
    assert pages.find_ats_board('<a href="https://job-boards.greenhouse.io/umbra">Jobs</a>') == (
        "greenhouse", "umbra",
    )
    assert pages.find_ats_board('<iframe src="https://jobs.ashbyhq.com/cafe-x"></iframe>') == (
        "ashby", "cafe-x",
    )
    assert pages.find_ats_board('<a href="https://apply.workable.com/shop-y/">') == (
        "workable", "shop-y",
    )
    assert pages.find_ats_board(_careers()) is None
