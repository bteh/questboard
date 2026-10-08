"""Places I'd work at: hosted boards read through their own APIs.

Fixtures are live responses captured 2026-10-08 (unused fields dropped):
Alfred on Rippling, Uniqlo on Workday, Verve Coffee on ADP Workforce Now,
Bluestone Lane on Paylocity. The owner's brother is job hunting in the San
Gabriel Valley and North Orange County, so the Uniqlo and Bluestone cases
pin Arcadia, Brea, and Orange. No live HTTP.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import _hosted_boards as boards  # noqa: E402
from job_finder.tools.scrapers import watched_pages as wp  # noqa: E402
from job_finder.tools.scrapers._polite_fetch import FetchError  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
ALFRED_URL = "https://ats.rippling.com/alfred/jobs"
UNIQLO_URL = "https://fastretailing.wd3.myworkdayjobs.com/retail_us_Uniqlo"
VERVE_URL = (
    "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
    "?cid=6915c399-128d-4976-932a-0870c48dc09d&ccId=19000101_000001&lang=en_US"
)
BLUESTONE_URL = (
    "https://recruiting.paylocity.com/recruiting/jobs/All/"
    "1e51c5cd-10b5-429d-a2d3-1ea0e01bb49c/BLUESTONE-LANE-NY-LLC"
)


def _replay(shop: str) -> SimpleNamespace:
    data = json.loads((FIXTURES / f"hosted_{shop}.json").read_text(encoding="utf-8"))
    answers = {
        (ex["url"], json.dumps(ex["body"], sort_keys=True)): ex.get("json", ex.get("html"))
        for ex in data["exchanges"]
    }
    calls: list[str] = []

    def fetch(url: str, body: dict | None = None):
        calls.append(url)
        key = (url, json.dumps(body, sort_keys=True))
        if key not in answers:
            raise FetchError("not in fixture")
        return answers[key]

    return SimpleNamespace(fetch=fetch, calls=calls)


def _read(shop: str, url: str, near) -> tuple[int, list[dict]]:
    site = _replay(shop)
    board = boards.find_board(url)
    return boards.read_board(board, near, fetch_json=site.fetch, fetch_html=site.fetch)


def _kept(rows: list[dict]) -> dict[str, dict]:
    return {r["title"]: r for r in rows if wp.keep_row(r)}


def _in(*cities: str):
    return lambda where: any(c in where for c in cities)


def test_board_urls_are_recognized():
    assert boards.find_board(ALFRED_URL) == boards.Board("rippling", {"slug": "alfred"})
    assert boards.find_board(
        "https://api.rippling.com/platform/api/ats/v1/board/alfred/jobs"
    ).ref == {"slug": "alfred"}
    uniqlo = boards.find_board(UNIQLO_URL)
    assert uniqlo.kind == "workday"
    assert (uniqlo.ref["tenant"], uniqlo.ref["site_id"]) == ("fastretailing", "retail_us_Uniqlo")
    assert boards.find_board(VERVE_URL) == boards.Board(
        "adp", {"cid": "6915c399-128d-4976-932a-0870c48dc09d", "ccid": "19000101_000001"},
    )
    assert boards.find_board(BLUESTONE_URL) == boards.Board(
        "paylocity", {"guid": "1e51c5cd-10b5-429d-a2d3-1ea0e01bb49c"},
    )


def test_shop_page_linking_adp_is_recognized():
    """vervecoffee.com/pages/careers links its ADP board with &amp; in the href."""
    html = ('<a href="https://workforcenow.adp.com/mascsr/default/mdf/recruitment/'
            'recruitment.html?cid=6915c399-128d-4976-932a-0870c48dc09d&amp;ccId=19000101_000001'
            '&amp;lang=en_US">Careers</a>')
    assert boards.find_board(html).ref["cid"] == "6915c399-128d-4976-932a-0870c48dc09d"


def test_ukg_boards_have_no_reader():
    """H Mart and Daiso: recruiting.ultipro.com robots.txt disallows the API."""
    assert boards.find_board(
        "https://recruiting.ultipro.com/HMA1000HMGBC/JobBoardView/LoadSearchResults"
    ) is None


def test_alfred_keeps_hourly_shifts_drops_salaried():
    found, rows = _read("alfred", ALFRED_URL, _in("Los Angeles", "Beverly Hills"))
    assert found == 10
    kept = _kept(rows)
    assert set(kept) == {
        "Beverly & Martel PT Shift Lead", "Canon Drive PT Barista", "Payroll Specialist",
    }
    barista = kept["Canon Drive PT Barista"]
    assert (barista["salary_min"], barista["salary_max"], barista["salary_period"]) == (
        18.67, 18.67, "hourly",
    )
    assert barista["employment"] == "parttime"
    assert barista["location"] == "Beverly Hills, CA"
    assert barista["date_posted"]
    assert barista["url"].startswith("https://ats.rippling.com/alfred/jobs/")
    manager = next(r for r in rows if r["title"] == "Cafe Manager in Training")
    assert (manager["salary_min"], manager["salary_period"]) == (70304.0, "yearly")


def test_uniqlo_arcadia_and_brea_store_shifts():
    found, rows = _read("uniqlo", UNIQLO_URL, _in("Arcadia"))
    assert found == 336
    kept = _kept(rows)
    assert set(kept) == {
        "Loss Prevention Agent (Full-Time) - Westfield Santa Anita",
        "UNIQLO Retail Sales Associate (Seasonal Part-Time) - The Shops at Santa Anita",
    }
    seasonal = kept["UNIQLO Retail Sales Associate (Seasonal Part-Time) - The Shops at Santa Anita"]
    assert (seasonal["salary_min"], seasonal["salary_period"]) == (18.5, "hourly")
    assert seasonal["employment"] == "parttime"
    assert seasonal["url"].startswith(UNIQLO_URL + "/job/Arcadia-CA/")

    _, brea = _read("uniqlo", UNIQLO_URL, _in("Brea"))
    assert [(r["location"], r["salary_min"]) for r in brea if wp.keep_row(r)] == [
        ("Brea,CA", 17.5), ("Brea,CA", 17.5),
    ]


def test_uniqlo_pages_through_the_whole_board():
    site = _replay("uniqlo")
    boards.read_workday(boards.find_board(UNIQLO_URL).ref, _in("Arcadia"), site.fetch)
    listing_calls = [u for u in site.calls if u.endswith("/jobs")]
    assert len(listing_calls) == 17


def test_verve_states_hourly_ranges_drops_annual():
    found, rows = _read("verve", VERVE_URL, _in("Los Angeles"))
    assert found == 27
    kept = _kept(rows)
    assert "Chief Growth Officer" not in kept
    assert "Regional Wholesale Sales Manager SoCal" not in kept
    barista = kept["Barista - West 3rd"]
    assert (barista["salary_min"], barista["salary_max"], barista["salary_period"]) == (
        18.4, 19.65, "hourly",
    )
    assert "jobId=64296058" in barista["url"]
    # minimumRate 0.0 means ADP states only the top of the range
    lead = kept["Culinary Shift Lead"]
    assert (lead["salary_min"], lead["salary_max"]) == (22.0, 22.0)


def test_bluestone_old_towne_orange_reads_detail_jsonld():
    found, rows = _read("bluestone", BLUESTONE_URL, _in("Orange, CA"))
    assert found == 88
    kept = _kept(rows)
    assert set(kept) == {"Cook", "Service Professional"}
    service = kept["Service Professional"]
    assert (service["salary_min"], service["salary_max"], service["salary_period"]) == (
        20.0, 25.0, "hourly",
    )
    assert service["url"] == "https://recruiting.paylocity.com/Recruiting/Jobs/Details/3635316"


def test_watched_board_url_reads_the_board_not_the_page():
    site = _replay("alfred")
    page_fetches: list[str] = []
    result = wp.check_page(
        ALFRED_URL, "Los Angeles, CA",
        fetch=lambda url: page_fetches.append(url) or "",
        board_read=lambda board, near: boards.read_board(board, near, fetch_json=site.fetch),
    )
    assert page_fetches == []
    assert result["via"] == "rippling"
    assert result["name"] == "Alfred"
    assert result["found"] == 10
    titles = {r["title"] for r in result["rows"]}
    assert "Beverly & Martel PT Shift Lead" in titles
    assert "Cafe Manager in Training" not in titles
    for row in result["rows"]:
        assert row["company"] == "Alfred"
        assert row["source"] == "watched-pages"


def test_board_failure_is_a_plain_error():
    def broken(board, near):
        raise FetchError("That site's robots.txt asks tools not to read this page.")

    result = wp.check_page(UNIQLO_URL, "Los Angeles, CA", board_read=broken)
    assert result["rows"] == []
    assert "robots.txt" in result["error"]


def test_san_gabriel_valley_area_keeps_arcadia():
    pytest.importorskip("job_finder.place_areas")
    site = _replay("uniqlo")
    result = wp.check_page(
        UNIQLO_URL, "San Gabriel Valley (626)",
        board_read=lambda board, near: boards.read_board(board, near, fetch_json=site.fetch),
    )
    assert {r["location"] for r in result["rows"]} == {"Arcadia, CA"}


def test_new_shops_are_starter_suggestions():
    starters = {s["name"]: s["url"] for s in wp.starter_list()}
    assert starters["Alfred"] == ALFRED_URL
    assert starters["Uniqlo"] == UNIQLO_URL
    assert starters["Verve Coffee"] == VERVE_URL
    assert starters["Bluestone Lane"] == BLUESTONE_URL
    for url in starters.values():
        assert "ultipro" not in url


def test_fetch_json_obeys_robots(monkeypatch):
    from job_finder.tools.scrapers import _polite_fetch

    monkeypatch.setattr(_polite_fetch, "robots_allows", lambda url: False)
    with pytest.raises(FetchError):
        _polite_fetch.fetch_json("https://recruiting.ultipro.com/X/JobBoardView/LoadSearchResults", {})
