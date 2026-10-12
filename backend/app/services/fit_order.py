"""The one ordering rule for the assistant's ranked fit picks.

Verdict tier first (strong, good, reach), the assistant's rank inside a tier.
Each assistant session writes its ranks as global positions, so ordering by
rank alone let a newer session's reach pick sit above an older session's
strong pick (Oct 12 2026 board audit, tests/test_board_audit_oct12.py).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")

TIER_ORDER: tuple[str, ...] = ("strong", "good", "reach")
_UNKNOWN_TIER = len(TIER_ORDER)
_NO_RANK = 1_000_000


def verdict_tier(verdict: Any) -> int:
    try:
        return TIER_ORDER.index(str(verdict or "").lower())
    except ValueError:
        return _UNKNOWN_TIER


def fit_sort_key(verdict: Any, rank: Any) -> tuple[int, int]:
    usable_rank = rank if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0 else _NO_RANK
    return verdict_tier(verdict), usable_rank


def order_by_tier(items: Iterable[T], verdict_of: Callable[[T], Any]) -> list[T]:
    """Stable regroup by tier: the order inside each tier is kept as given."""
    return sorted(items, key=lambda item: verdict_tier(verdict_of(item)))


def split_by_tier(items: Iterable[T], verdict_of: Callable[[T], Any]) -> list[list[T]]:
    """Consecutive tier segments of an already tier-ordered list."""
    segments: list[list[T]] = []
    last_tier: int | None = None
    for item in items:
        tier = verdict_tier(verdict_of(item))
        if tier != last_tier:
            segments.append([])
            last_tier = tier
        segments[-1].append(item)
    return segments
