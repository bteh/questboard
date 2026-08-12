"""The quest-kind registry, Python side.

packages/kinds/kinds.json is the single source of truth shared with the
frontend (@questboard/kinds). This module only loads and indexes it.
tests/test_kinds.py pins the contract so the two sides cannot drift.

Adding a kind: edit kinds.json (plus a stamp in @questboard/ui). Adding a
source: one decorated file in tools/scrapers with kind="<id>"; the decorator
validates the id against this registry at import time.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
_KINDS_JSON = _BUNDLE_ROOT / "packages" / "kinds" / "kinds.json"


@dataclass(frozen=True)
class Facet:
    """A kind's own sub-filter: terms match a row's title and description."""

    id: str
    label: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Kind:
    id: str
    label: str
    sub: str
    hue: str
    order: int
    legacy_verticals: tuple[str, ...]
    facets: tuple[Facet, ...] = ()


@lru_cache(maxsize=1)
def get_kinds() -> tuple[Kind, ...]:
    """All kinds, sorted by display order."""
    with open(_KINDS_JSON, encoding="utf-8") as fh:
        raw = json.load(fh)
    kinds = [
        Kind(
            id=entry["id"],
            label=entry["label"],
            sub=entry["sub"],
            hue=entry["hue"],
            order=entry["order"],
            legacy_verticals=tuple(entry["legacy_verticals"]),
            facets=tuple(
                Facet(id=f["id"], label=f["label"], terms=tuple(f["terms"]))
                for f in entry.get("facets", [])
            ),
        )
        for entry in raw["kinds"]
    ]
    return tuple(sorted(kinds, key=lambda k: k.order))


@lru_cache(maxsize=1)
def _vertical_index() -> dict[str, Kind]:
    index: dict[str, Kind] = {}
    for kind in get_kinds():
        index[kind.id] = kind
        for legacy in kind.legacy_verticals:
            index[legacy] = kind
    return index


def kind_for_vertical(vertical: str) -> Kind | None:
    """Resolve a stored vertical value (legacy or kind id) to its kind."""
    return _vertical_index().get(vertical)


def known_vertical_values() -> set[str]:
    """Every value a scraper may register or a record may carry (kind ids + legacy)."""
    return set(_vertical_index().keys())


def vertical_values_for(kind_id: str) -> list[str]:
    """Every stored value a kind answers to, for queries against old rows."""
    for kind in get_kinds():
        if kind.id == kind_id:
            return [kind.id, *kind.legacy_verticals]
    return []


def facet_for(vertical: str, facet_id: str) -> Facet | None:
    """A kind's facet by id; the kind may be named by a legacy spelling."""
    kind = kind_for_vertical(vertical)
    if kind is None:
        return None
    for facet in kind.facets:
        if facet.id == facet_id:
            return facet
    return None
