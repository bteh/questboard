"""Unit pins for the Oct 12 2026 fit-order and searched-roles helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


def test_tier_beats_rank_and_rank_orders_inside_a_tier() -> None:
    from app.services.fit_order import fit_sort_key

    picks = [("reach", 1), ("good", 2), ("strong", 30), ("strong", 4), ("good", None)]
    ordered = sorted(picks, key=lambda p: fit_sort_key(*p))
    assert ordered == [("strong", 4), ("strong", 30), ("good", 2), ("good", None), ("reach", 1)]


def test_proposal_keeps_every_saved_role_and_drops_extras_past_the_cap() -> None:
    from app.services.searched_role_proposals import proposed_role_list

    saved = ["A", "B", "C"]
    assert proposed_role_list(saved, ["a", "D", "E", "F"], cap=5) == ["A", "B", "C", "D", "E"]
    assert proposed_role_list(saved, ["b", "C"], cap=5) is None
    assert proposed_role_list(saved, ["D"], cap=3) is None
