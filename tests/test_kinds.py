"""The kinds registry contract: kinds.json is the single source of truth,
this side must load it faithfully, and every registered scraper must sit in
a known lane. The frontend pins the same contract from its side in
packages/kinds/src/index.test.ts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from job_finder.kinds import (  # noqa: E402
    _KINDS_JSON,
    get_kinds,
    kind_for_vertical,
    known_vertical_values,
    vertical_values_for,
)


def test_loader_matches_the_json_exactly():
    raw = json.loads(Path(_KINDS_JSON).read_text(encoding="utf-8"))
    kinds = get_kinds()
    assert len(kinds) == len(raw["kinds"])
    by_id = {entry["id"]: entry for entry in raw["kinds"]}
    for kind in kinds:
        entry = by_id[kind.id]
        assert kind.label == entry["label"]
        assert kind.sub == entry["sub"]
        assert kind.hue == entry["hue"]
        assert kind.order == entry["order"]
        assert list(kind.legacy_verticals) == entry["legacy_verticals"]


def test_ids_and_orders_are_unique_and_sorted():
    kinds = get_kinds()
    ids = [k.id for k in kinds]
    orders = [k.order for k in kinds]
    assert len(set(ids)) == len(ids)
    assert len(set(orders)) == len(orders)
    assert orders == sorted(orders)


def test_legacy_verticals_map_where_the_old_data_expects():
    # career split into its own `work` lane so the default quest board
    # never shows job postings; lens (freelance/gigs) stays under skill
    assert kind_for_vertical("career").id == "work"
    assert kind_for_vertical("lens").id == "skill"
    assert kind_for_vertical("study").id == "think"
    assert kind_for_vertical("camera").id == "perform"
    assert kind_for_vertical("party").id == "party"
    # kind ids resolve to themselves so new sources can write them directly
    for kind in get_kinds():
        assert kind_for_vertical(kind.id).id == kind.id
    assert kind_for_vertical("personal") is None  # the log's lane, never a board kind


def test_no_legacy_vertical_claimed_twice():
    seen: dict[str, str] = {}
    for kind in get_kinds():
        for legacy in kind.legacy_verticals:
            assert legacy not in seen, f"{legacy!r} claimed by {seen[legacy]} and {kind.id}"
            seen[legacy] = kind.id


def test_vertical_value_expansion_for_queries():
    assert sorted(vertical_values_for("skill")) == ["lens", "skill"]
    assert sorted(vertical_values_for("work")) == ["career", "work"]
    assert vertical_values_for("nope") == []


def test_every_registered_scraper_sits_in_a_known_lane():
    import job_finder.tools.scrapers  # noqa: F401 — importing the package loads every plugin
    from job_finder.tools.scrapers._registry import get_registry

    known = known_vertical_values()
    for name, meta in get_registry().items():
        assert meta.vertical in known, f"scraper {name!r} in unknown lane {meta.vertical!r}"


def test_registering_an_unknown_kind_fails_at_import_time():
    from job_finder.tools.scrapers._registry import register_scraper

    with pytest.raises(ValueError, match="unknown kind"):
        register_scraper(
            name="bogus-src",
            display_name="Bogus",
            url="https://example.com",
            kind="not-a-kind",
        )(lambda: None)
