"""Lane adjacency needs an anchor word, not just a context word.

Real case (Sep 22 2026): Brian's saved roles were eleven data leadership
titles (Data Engineering Manager, Data Operations Manager, Manager, Business
Intelligence, AI Platform Manager, ...). In the "posted last 7 days" view
about 12 of 44 rows were noise the lane admitted because a title shared ONE
word with a saved role. "operations" from Data Operations Manager let in
"Procurement Operations Manager" (Anduril), "HR & Legal Technology Operations
Manager" and "Content Operations Manager". "business" from Manager, Business
Intelligence let in "Business Development Manager" and "Business Operations &
Strategy Manager". "ai" from AI Platform Manager let in "Engagement Manager,
AI Implementations". "engineering" and "platform" let in "Engineering
Manager, 3D Platform" and "Engineering Manager, Perception AI".

Rule under test: words that describe context rather than a profession
(operations, business, engineering, platform, ai, technology, ...) never
qualify a title on their own. An adjacent match needs a shared word outside
that set, or at least two shared words. A full role match is unchanged, and
so is the occupation-conflict logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

SAVED_ROLES = [
    "Data Engineering Manager",
    "Analytics Engineering Manager",
    "Data Platform Manager",
    "Data Operations Manager",
    "Data Engineering Lead",
    "Analytics Engineering Lead",
    "Senior Manager, Data Engineering",
    "Manager, Business Intelligence",
    "Data Governance Manager",
    "AI Platform Manager",
    "Staff Data Engineer",
]

CONTEXT_WORDS = [
    "operations", "ops", "business", "engineering", "platform", "ai",
    "technology", "technical", "product", "program", "project", "strategy",
    "solutions", "systems", "services", "digital", "enterprise", "global",
    "growth",
]

NOISE_TITLES = [
    "Procurement Operations Manager",
    "Business Development Manager",
    "Business Operations & Strategy Manager",
    "HR & Legal Technology Operations Manager",
    "Engagement Manager, AI Implementations",
    "Engineering Manager, 3D Platform",
    "Engineering Manager, Perception AI",
    "Content Operations Manager",
]

IN_LANE_TITLES = [
    "Senior Manager, Data Strategy",
    "Manager, Business Analytics",
    "Engineering Manager, Data Feeds",
    "Data & Analytics Technical Lead",
    "AI Platform Engineering Manager",
    "Analytics Lead, Full Stack (Strategic Revenue Insights)",
    "Lead Data Engineer",
    "Data Engineering Manager, Regulatory Compliance",
    "Staff Data Engineer, Analytics",
    "Business Intelligence (BI) Manager",
]


def test_context_words_are_a_named_pinned_set() -> None:
    from app.services import local_agent_service as las

    for word in CONTEXT_WORDS:
        # _role_tokens folds "operations" to "ops" and "engineering" to
        # "engineer"; the set must hold the folded form the lane compares on.
        assert las._role_tokens(word) <= las._LANE_CONTEXT_TOKENS, word
    assert not (las._LANE_CONTEXT_TOKENS & {"data", "analytics", "marketing", "governance"})


@pytest.mark.parametrize("title", NOISE_TITLES)
def test_one_shared_context_word_does_not_put_a_title_in_lane(title: str) -> None:
    from app.services import local_agent_service as las

    assert not las._title_is_in_lane(title, SAVED_ROLES), title


@pytest.mark.parametrize("title", IN_LANE_TITLES)
def test_an_anchor_word_or_two_shared_words_keeps_a_title_in_lane(title: str) -> None:
    from app.services import local_agent_service as las

    assert las._title_is_in_lane(title, SAVED_ROLES), title


def test_rule_is_profession_agnostic() -> None:
    from app.services import local_agent_service as las

    roles = ["Product Marketing Manager", "Growth Marketing Lead"]
    assert las._title_is_in_lane("Marketing Manager", roles)
    assert not las._title_is_in_lane("Growth Manager", roles)
