"""Contract tests for the r/LAjobs scraper (odd kind, casting rows to perform).

Fixture is 20 REAL posts from
https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=LAjobs
captured live 2026-10-08, picked to cover each gate. No live HTTP.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "reddit_lajobs_posts.json"


@pytest.fixture()
def mod():
    from job_finder.tools.scrapers import reddit_lajobs

    return reddit_lajobs


def _search(mod, payload: object, **kw) -> list[dict]:
    kw.setdefault("max_days_old", 3650)
    with patch.object(mod, "_get_json", return_value=payload):
        return mod.search_reddit_lajobs(**kw)


@pytest.fixture()
def rows(mod) -> list[dict]:
    return _search(mod, json.loads(FIXTURE.read_text(encoding="utf-8")))


def _by_title(rows: list[dict], prefix: str) -> dict:
    hits = [r for r in rows if r["title"].startswith(prefix)]
    assert hits, f"no row titled {prefix!r}"
    return hits[0]


def test_keeps_exactly_the_hiring_side(rows) -> None:
    assert sorted(r["title"][:30] for r in rows) == sorted([
        "Need one-time training for Ric",
        "[Hiring] Live Shopping Host – ",
        "[Hiring] 🇺🇸 Los Angeles — Remo",
        "$20/hr — Part-Time Horticultur",
        "Seeking female Actress or Mode",
        "Truck Driver needed",
        "Line Cooks Wanted",
        "[HIRING] South Bay LA | Bounce",
    ])


def test_job_seekers_and_for_hire_posts_are_dropped(rows) -> None:
    titles = " ".join(r["title"].lower() for r in rows)
    for seeker in ("looking for work", "for hire", "electrical helper",
                   "anyone hiring", "handyman"):
        assert seeker not in titles


def test_house_rules_and_career_roles_are_dropped(rows) -> None:
    titles = " ".join(r["title"].lower() for r in rows)
    # adult work, a car-decal scam, a lease handoff, a $72k salaried role,
    # and a monthly-pay driver pitch
    for dropped in ("fetish", "job offer", "social community", "la galaxy", "uber"):
        assert dropped not in titles


def test_casting_posts_route_to_perform(rows) -> None:
    assert _by_title(rows, "Seeking female Actress")["vertical"] == "perform"
    assert _by_title(rows, "[Hiring] Live Shopping Host")["vertical"] == "perform"
    assert _by_title(rows, "Truck Driver needed")["vertical"] == "odd"


def test_location_defaults_to_la_unless_stated(rows) -> None:
    assert _by_title(rows, "Truck Driver needed")["location"] == "Los Angeles, CA"
    assert _by_title(rows, "[Hiring] Live Shopping Host")["location"] == "Orange County, CA"


def test_pay_only_when_stated(rows) -> None:
    cooks = _by_title(rows, "Line Cooks Wanted")
    assert cooks["quest"]["pay_note"] == "$21/hour"
    assert cooks["salary_min"] == 21.0 and cooks["salary_period"] == "hourly"
    bounce = _by_title(rows, "[HIRING] South Bay LA")
    assert bounce["salary_min"] == 200.0 and bounce["salary_max"] == 500.0
    embroidery = _by_title(rows, "Need one-time training")
    assert "quest" not in embroidery and "salary_min" not in embroidery


def test_cards_say_reddit_and_link_the_thread(rows) -> None:
    from job_finder.row_contract import validate_rows
    from job_finder.tools.scrapers import get_registry

    meta = get_registry()["reddit-lajobs"]
    assert meta.display_name == "Reddit"
    assert meta.research_only is False
    valid, rejected = validate_rows(rows, meta)
    assert rejected == []
    for row in rows:
        assert row["source"] == "reddit-lajobs"
        assert row["url"].startswith("https://www.reddit.com/r/LAjobs/comments/")
        assert row["date_posted"]


def test_old_posts_are_skipped(mod) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _search(mod, payload, max_days_old=1) == []


def test_bad_payload_is_empty(mod) -> None:
    assert _search(mod, None) == []
    assert _search(mod, {"data": "nope"}) == []
