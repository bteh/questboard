"""Contract tests for the static LA link cards: Central Casting and Qwick.

Central Casting's jobs-la page disallows every crawler in robots.txt, and
Qwick shows no open shifts without an account, so both are one static row
with no network. These pin the URL, the kind, and that no pay is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

CASES = [
    ("centralcasting_onramp", "search_centralcasting_onramp", "perform",
     "https://blog.centralcasting.com/jobs-la/"),
    ("qwick_onramp", "search_qwick_onramp", "odd",
     "https://www.qwick.com/market/california/los-angeles/"),
]


@pytest.mark.parametrize("name,fn,kind,url", CASES)
def test_one_static_card(name, fn, kind, url, monkeypatch) -> None:
    import importlib

    import requests

    def no_network(*a, **kw):
        raise AssertionError("link cards must not fetch")

    monkeypatch.setattr(requests, "get", no_network)
    mod = importlib.import_module(f"job_finder.tools.scrapers.{name}")
    rows = getattr(mod, fn)()
    assert len(rows) == 1
    row = rows[0]
    assert row["url"] == url
    assert row["vertical"] == kind
    assert row["source"] == name
    assert row["location"] == "Los Angeles, CA"
    assert row["salary_min"] is None and row["salary_max"] is None
    for value in list(row.values()) + list(row["quest"].values()):
        if isinstance(value, str):
            assert "$" not in value
            assert "—" not in value
    assert getattr(mod, fn)(max_results=0) == []


@pytest.mark.parametrize("name,fn,kind,url", CASES)
def test_registration(name, fn, kind, url) -> None:
    from job_finder.row_contract import validate_rows
    from job_finder.tools.scrapers._registry import default_scraper_names, get_registry
    import importlib

    meta = get_registry()[name]
    assert meta.vertical == kind
    assert meta.full_snapshot
    assert not meta.research_only
    assert name not in default_scraper_names()
    mod = importlib.import_module(f"job_finder.tools.scrapers.{name}")
    valid, rejected = validate_rows(getattr(mod, fn)(), meta)
    assert rejected == [] and len(valid) == 1
