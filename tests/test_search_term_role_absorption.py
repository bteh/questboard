"""A keyword phrase must never absorb a saved target role.

Real case (Brian, Sep 9 2026): roles "Data Engineering Manager", "Data
Platform Manager", "Data Products Manager" alongside the keyword phrases
"data engineering", "data platform", "data products". The API merges
title-shaped keywords into the roles list, and Phase 1b of
``_consolidate_search_terms`` treated "data engineering manager" as covered
by the broader "data engineering". Two runs never asked Indeed or LinkedIn
for a single manager title; every query returned 62 IC "Data Engineer" rows.

Rule under test: a shorter query may absorb a longer one only when the
extra words add no role-type token ("manager", "lead", "director", ...).
Seniority variants of the same title still collapse as before.
"""

from __future__ import annotations

from job_finder.pipeline import _build_search_terms, _consolidate_search_terms


def _lowered(terms: list[str]) -> set[str]:
    return {t.lower() for t in terms}


BRIAN_ROLES = [
    "Data Engineering Manager",
    "Data Platform Manager",
    "Data Products Manager",
    "Data Engineering Lead",
]
BRIAN_PHRASES = ["data engineering", "data platform", "data products", "data pipeline"]


def test_keyword_phrase_never_absorbs_saved_manager_title() -> None:
    # The API path merges title-shaped keywords into roles before consolidation.
    merged = BRIAN_ROLES + BRIAN_PHRASES
    terms = _lowered(_consolidate_search_terms(merged, [], config={}))
    assert {
        "data engineering manager",
        "data platform manager",
        "data products manager",
        "data engineering lead",
    } <= terms


def test_explicit_roles_path_keeps_manager_titles_end_to_end() -> None:
    config = {
        "target_roles": BRIAN_ROLES,
        "keyword_searches": BRIAN_PHRASES,
        "keywords": {"technical": ["Python", "AWS", "Apache Airflow"]},
    }
    terms, _, _ = _build_search_terms(config, roles=BRIAN_ROLES + BRIAN_PHRASES)
    lowered = _lowered(terms)
    assert "data engineering manager" in lowered
    assert "data platform manager" in lowered
    assert "data products manager" in lowered


def test_seniority_variants_of_one_title_still_collapse() -> None:
    terms = _consolidate_search_terms(
        ["Senior Product Manager", "Product Manager", "Staff Product Manager"],
        [],
        config={},
    )
    assert [t.lower() for t in terms] == ["product manager"]


def test_broader_title_still_absorbs_a_domain_suffix_variant() -> None:
    # "operations" adds no role-type token, so the broader title still covers it.
    terms = _consolidate_search_terms(
        ["Product Manager", "Product Manager Operations"],
        [],
        config={},
    )
    assert [t.lower() for t in terms] == ["product manager"]


def test_keyword_path_role_query_cannot_absorb_a_role_type_keyword() -> None:
    # CLI path: roles and keyword_searches arrive separately. The single-word
    # base "sales" still covers "sales enablement" but not "sales manager".
    terms = _lowered(
        _consolidate_search_terms(
            ["VP Sales", "Head of Sales"],
            ["sales enablement", "sales manager"],
            config={},
        )
    )
    assert "sales manager" in terms
    assert "sales enablement" not in terms


def test_keyword_inflection_of_a_role_still_collapses() -> None:
    # "engineering" is an inflection of "engineer", not a new role type.
    terms = _consolidate_search_terms(["Data Engineer"], ["data engineering"], config={})
    assert [t.lower() for t in terms] == ["data engineer"]
