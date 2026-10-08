"""Contract tests for the r/castingcalls scraper (perform kind).

Fixture is 16 REAL posts from
https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=castingcalls
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

FIXTURE = ROOT / "tests" / "fixtures" / "reddit_castingcalls_posts.json"


@pytest.fixture()
def mod():
    from job_finder.tools.scrapers import reddit_castingcalls

    return reddit_castingcalls


def _search(mod, payload: object, **kw) -> list[dict]:
    kw.setdefault("max_days_old", 3650)
    with patch.object(mod, "_get_json", return_value=payload):
        return mod.search_reddit_castingcalls(**kw)


@pytest.fixture()
def rows(mod) -> list[dict]:
    return _search(mod, json.loads(FIXTURE.read_text(encoding="utf-8")))


def _by_title(rows: list[dict], prefix: str) -> dict:
    hits = [r for r in rows if r["title"].startswith(prefix)]
    assert hits, f"no row titled {prefix!r}"
    return hits[0]


def test_keeps_only_casting_calls(rows) -> None:
    assert sorted(r["title"][:30] for r in rows) == sorted([
        "Casting call for 3 roles in Se",
        "Istanbul Casting Call — Models",
        "Casting nationwide - Project A",
    ])


def test_self_promo_questions_and_site_ads_are_dropped(rows) -> None:
    titles = " ".join(r["title"].lower() for r in rows)
    for dropped in ("hire me", "looking for role", "has anyone heard", "in seconds"):
        assert dropped not in titles


def test_unpaid_adult_and_removed_calls_are_dropped(rows) -> None:
    titles = " ".join(r["title"].lower() for r in rows)
    # "No pay" in body, "No-Budget", "(unpaid)", boudoir, a [removed] body
    for dropped in ("female lead", "the millers", "48 hour", "boudoir",
                    "street interview", "casting actors wanted",
                    "casting actors and actresses"):
        assert dropped not in titles


def test_location_only_when_stated(rows) -> None:
    assert _by_title(rows, "Casting call for 3 roles")["location"] == "Seattle, WA"
    assert _by_title(rows, "Istanbul Casting Call")["location"] == "Istanbul, Turkey"
    assert all(r["location"] != "Los Angeles, CA" for r in rows)


def test_location_is_blank_when_unstated(mod) -> None:
    post = {
        "title": "Casting call: voice actors needed",
        "selftext": "Three roles, $50 each.",
        "url": "https://www.reddit.com/r/CastingCalls/comments/abc/x/",
        "author": "someone",
        "created_utc": 1791000000,
    }
    rows = _search(mod, {"data": [post]})
    assert rows[0]["location"] == ""
    assert rows[0]["quest"]["pay_note"] == "$50"
    post["title"] = "Now casting extras in Burbank"
    assert _search(mod, {"data": [post]})[0]["location"] == "Los Angeles, CA"


def test_pay_only_when_stated(rows) -> None:
    seattle = _by_title(rows, "Casting call for 3 roles")
    assert seattle["quest"]["pay_note"] == "$150"
    assert "salary_min" not in seattle
    nationwide = _by_title(rows, "Casting nationwide")
    assert nationwide["salary_min"] == 1000.0 and nationwide["salary_period"] == "daily"
    assert "quest" not in _by_title(rows, "Istanbul Casting Call")


def test_cards_say_reddit_and_pass_the_row_contract(rows) -> None:
    from job_finder.row_contract import validate_rows
    from job_finder.tools.scrapers import get_registry

    meta = get_registry()["reddit-castingcalls"]
    assert meta.display_name == "Reddit"
    assert meta.vertical == "perform"
    assert meta.research_only is False
    valid, rejected = validate_rows(rows, meta)
    assert rejected == []
    assert all(r["vertical"] == "perform" for r in rows)
