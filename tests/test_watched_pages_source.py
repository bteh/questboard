"""Places I'd work at: the watched-pages source (parttime kind).

Owner case, 2026-10-08: ELOREA's Koreatown barista shift
(elorea.com/pages/barista-la) lives only on the shop's own careers page.
Fixtures are the real ELOREA pages (see test_careers_page.py). No live HTTP.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURES = ROOT / "tests" / "fixtures"
CAREERS_URL = "https://elorea.com/pages/career-opportunities"
BARISTA_URL = "https://elorea.com/pages/barista-la"
KTOWN = "Koreatown, Los Angeles, CA"


@pytest.fixture()
def mod():
    from job_finder.tools.scrapers import watched_pages

    return watched_pages


@pytest.fixture()
def site():
    pages = {
        CAREERS_URL: (FIXTURES / "elorea_careers.html").read_text(encoding="utf-8"),
        BARISTA_URL: (FIXTURES / "elorea_barista_la.html").read_text(encoding="utf-8"),
    }
    calls: list[str] = []

    def fetch(url: str) -> str:
        from job_finder.tools.scrapers._polite_fetch import FetchError

        calls.append(url)
        if url not in pages:
            raise FetchError("not in fixture")
        return pages[url]

    return SimpleNamespace(fetch=fetch, calls=calls)


def test_elorea_la_roles_kept_with_stated_pay(mod, site):
    result = mod.check_page(CAREERS_URL, KTOWN, fetch=site.fetch)
    assert result["error"] == ""
    assert result["name"] == "ELOREA"
    assert result["found"] == 6
    rows = {r["title"]: r for r in result["rows"]}
    assert set(rows) == {"Barista (LA)", "Scent Advisor (Sales Associate) LA"}
    barista = rows["Barista (LA)"]
    assert (barista["salary_min"], barista["salary_max"], barista["salary_period"]) == (
        22.0, 25.0, "hourly",
    )
    scent = rows["Scent Advisor (Sales Associate) LA"]
    assert (scent["salary_min"], scent["salary_max"], scent["salary_period"]) == (
        20.0, 25.0, "hourly",
    )
    for row in rows.values():
        assert row["company"] == "ELOREA"
        assert row["source"] == "watched-pages"
        assert row["vertical"] == "parttime"
        assert row["salary_source"] == "reported"
        assert row["location"] == "Koreatown, LA"
    assert barista["url"] == BARISTA_URL
    # the detail page filled the date and the posting's own text
    assert barista["date_posted"] == "2024-10-28"
    assert barista["description"].startswith("ELOREA is looking for a barista")


def test_elorea_nyc_roles_drop_for_an_la_place(mod, site):
    titles = {r["title"] for r in mod.check_page(CAREERS_URL, KTOWN, fetch=site.fetch)["rows"]}
    assert "Barista (NYC)" not in titles
    assert "Scent Advisor (Sales Associate) NY" not in titles
    # NYC detail pages are never fetched for an LA place
    assert "https://elorea.com/pages/barista" not in site.calls


def test_elorea_full_time_salaried_roles_drop(mod, site):
    ny = mod.check_page(CAREERS_URL, "New York, NY", fetch=site.fetch)
    titles = {r["title"] for r in ny["rows"]}
    assert titles == {"Barista (NYC)", "Scent Advisor (Sales Associate) NY"}
    assert "Director of Operations" not in titles
    assert "Head of Finance" not in titles
    assert "https://elorea.com/pages/director-of-supply-chain" not in site.calls


def test_no_saved_place_means_los_angeles(mod, site):
    titles = {r["title"] for r in mod.check_page(CAREERS_URL, None, fetch=site.fetch)["rows"]}
    assert titles == {"Barista (LA)", "Scent Advisor (Sales Associate) LA"}


def test_pasting_the_detail_page_itself_reads_its_jobposting(mod, site):
    """The owner pasted elorea.com/pages/barista-la directly."""
    result = mod.check_page(BARISTA_URL, KTOWN, fetch=site.fetch)
    assert result["via"] == "jobposting"
    assert [(r["title"], r["salary_min"], r["salary_max"]) for r in result["rows"]] == [
        ("Barista (LA)", 22.0, 25.0)
    ]


def test_ats_board_url_hands_off_without_reading_the_page(mod, site):
    """Blue Bottle Coffee posts on Lever; the existing Lever fetcher reads it."""
    handed: list[tuple[str, str]] = []

    def ats_fetch(ats: str, slug: str) -> list[dict]:
        handed.append((ats, slug))
        return [
            {"title": "Barista - Playa Vista", "company": "Bluebottlecoffee",
             "location": "Los Angeles, CA", "url": "https://jobs.lever.co/bluebottlecoffee/1",
             "salary_min": 20, "salary_max": 20, "salary_period": "hourly",
             "salary_currency": "USD", "description": "", "employment": ""},
            {"title": "Barista - Chicago", "company": "Bluebottlecoffee",
             "location": "Chicago, IL", "url": "https://jobs.lever.co/bluebottlecoffee/2",
             "salary_min": 17.68, "salary_max": 17.68, "salary_period": "hourly",
             "description": "", "employment": ""},
            {"title": "Finance Manager", "company": "Bluebottlecoffee",
             "location": "Los Angeles, CA", "url": "https://jobs.lever.co/bluebottlecoffee/3",
             "salary_min": 120000, "salary_max": 140000, "salary_period": "yearly",
             "description": "", "employment": "Full-time"},
        ]

    result = mod.check_page(
        "https://jobs.lever.co/bluebottlecoffee", KTOWN, "Blue Bottle Coffee",
        fetch=site.fetch, ats_fetch=ats_fetch,
    )
    assert handed == [("lever", "bluebottlecoffee")]
    assert site.calls == []
    assert result["via"] == "lever"
    assert [(r["title"], r["company"]) for r in result["rows"]] == [
        ("Barista - Playa Vista", "Blue Bottle Coffee")
    ]


def test_shop_page_linking_a_board_hands_off(mod):
    html = '<html><head><meta property="og:site_name" content="Cafe X"></head>' \
           '<body><a href="https://boards.greenhouse.io/cafex">Open roles</a></body></html>'
    handed: list[tuple[str, str]] = []
    result = mod.check_page(
        "https://cafex.com/careers", KTOWN,
        fetch=lambda url: html,
        ats_fetch=lambda ats, slug: handed.append((ats, slug)) or [],
    )
    assert handed == [("greenhouse", "cafex")]
    assert result["name"] == "Cafe X"


def test_robots_deny_skips_the_page(mod, monkeypatch):
    from job_finder.tools.scrapers import _polite_fetch

    _polite_fetch.clear_robots_cache()
    requested: list[str] = []

    def fake_get(url, **kwargs):
        requested.append(url)
        if url.endswith("/robots.txt"):
            return SimpleNamespace(status_code=200, text="User-agent: *\nDisallow: /careers\n")
        return SimpleNamespace(status_code=200, text="<html>jobs</html>")

    monkeypatch.setattr(_polite_fetch.requests, "get", fake_get)
    result = mod.check_page("https://blocked.example.com/careers", KTOWN)
    assert result["rows"] == []
    assert "robots.txt" in result["error"]
    assert requested == ["https://blocked.example.com/robots.txt"]

    assert _polite_fetch.fetch_html("https://blocked.example.com/about") == "<html>jobs</html>"
    _polite_fetch.clear_robots_cache()


def test_registered_as_their_site_on_the_parttime_lane(mod):
    from job_finder.tools.scrapers import get_registry

    meta = get_registry()[mod.SOURCE]
    assert meta.display_name == "Their site"
    assert meta.vertical == "parttime"
    assert meta.refresh_hours and meta.stale_after_days
    assert not meta.research_only


def test_starter_list_suggests_elorea(mod):
    starters = {s["name"]: s for s in mod.starter_list()}
    assert starters["ELOREA"]["url"] == CAREERS_URL
    for item in starters.values():
        assert item["url"].startswith("https://")
        assert item["area"] and item["hosting"]


def test_search_reads_every_watched_page_and_stamps_it(mod, monkeypatch, tmp_path):
    from job_finder.models import database, watched_pages as store

    database.init_db(str(tmp_path / "job_tracker.db"))
    session = database.get_session()
    store.save_page(session, CAREERS_URL, "ELOREA", 0)
    store.save_page(session, "https://gone.example.com/jobs", "Gone", 0)
    session.close()

    def fake_check(url, place, name=""):
        if "gone" in url:
            return {"name": name, "found": 0, "rows": [], "error": "Could not reach that page."}
        return {"name": name, "found": 6, "error": "", "rows": [
            {"title": "Barista (LA)", "url": BARISTA_URL, "source": mod.SOURCE},
        ]}

    monkeypatch.setattr(mod, "check_page", fake_check)
    sink: list[dict] = []
    rows = mod.search_watched_pages(place=KTOWN, partial_sink=sink)
    assert [r["title"] for r in rows] == ["Barista (LA)"]
    assert sink == rows

    stamped = {p["url"]: p for p in store.load_watched_pages()}
    assert stamped[CAREERS_URL]["last_found"] == 1
    assert stamped[CAREERS_URL]["last_checked_at"]
    assert stamped["https://gone.example.com/jobs"]["last_error"] == "Could not reach that page."


def test_lever_states_hourly_pay_and_commitment():
    """Blue Bottle's Lever Barista states salaryRange $20 per-hour-wage."""
    from job_finder.tools.scrapers.lever import _salary_range

    assert _salary_range({"min": 20, "max": 20, "currency": "USD",
                          "interval": "per-hour-wage"}) == {
        "salary_min": 20, "salary_max": 20, "salary_currency": "USD",
        "salary_period": "hourly", "salary_source": "reported",
    }
    assert _salary_range(None) == {"salary_min": None, "salary_max": None}
