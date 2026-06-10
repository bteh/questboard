"""Resume-derived terms must reach board search queries (profile-aware).

The user complaint: the 20 LLM-extracted resume skills in
``keywords.technical`` were used ONLY for scoring and never became search
queries, and ``_is_searchable_title`` silently dropped any keyword whose
words missed the hardcoded (tech-biased) token sets — so a nurse's "APRN"
or "phlebotomy" never reached a job board.

Fixes under test:
1. Title-shaped entries from ``keywords.technical`` merge into the search
   terms alongside ``keyword_searches`` (case-insensitive dedup).
2. ``_is_searchable_title`` accepts profile-harvested tokens so non-tech
   profiles aren't filtered by the tech-biased hardcoded sets.
3. Tech profiles behave exactly as before (skills like "rbac" stay out of
   board queries).
"""

from __future__ import annotations

import pytest

from job_finder.pipeline import (
    _build_search_terms,
    _is_searchable_title,
    _profile_title_tokens,
)


def _lowered(terms: list[str]) -> set[str]:
    return {t.lower() for t in terms}


# ── FIX: resume skills become search terms ──────────────────────────────────

def test_resume_skill_is_only_signal_still_searched() -> None:
    # Profile whose ONLY signal is an extracted resume skill.
    config = {"keywords": {"technical": ["nurse practitioner"]}}
    terms, _, _ = _build_search_terms(config)
    assert "nurse practitioner" in _lowered(terms)


def test_resume_skill_deduped_against_existing_terms() -> None:
    config = {
        "target_roles": ["Nurse Practitioner"],
        "keywords": {"technical": ["Nurse Practitioner"]},
    }
    terms, _, _ = _build_search_terms(config)
    assert sum(1 for t in terms if t.lower() == "nurse practitioner") == 1


def test_resume_skills_merge_on_explicit_roles_path_too() -> None:
    # The API passes roles explicitly (keywords already merged into them);
    # resume skills were never merged by the API so they must merge here.
    config = {"keywords": {"technical": ["data warehousing"]}}
    terms, _, _ = _build_search_terms(config, roles=["Data Engineer"])
    assert "data warehousing" in _lowered(terms)


def test_explicit_roles_path_does_not_reread_keyword_searches() -> None:
    # keyword_searches are already merged into roles by the API — re-reading
    # them here would double-count.
    config = {"keyword_searches": ["data platform"]}
    terms, _, _ = _build_search_terms(config, roles=["Data Engineer"])
    assert "data platform" not in _lowered(terms)


# ── FIX: profile-aware title detection (non-tech keywords survive) ─────────

def test_non_tech_keyword_aprn_not_silently_dropped() -> None:
    config = {
        "target_roles": ["Nurse Practitioner"],
        "keyword_searches": ["APRN"],
    }
    terms, _, _ = _build_search_terms(config)
    assert "aprn" in _lowered(terms)


def test_non_tech_skill_phlebotomy_not_silently_dropped() -> None:
    config = {
        "target_roles": ["Registered Nurse"],
        "keywords": {"technical": ["phlebotomy"]},
    }
    terms, _, _ = _build_search_terms(config)
    assert "phlebotomy" in _lowered(terms)


@pytest.mark.parametrize(
    ("term", "extra_tokens", "expected"),
    [
        ("APRN", frozenset({"aprn"}), True),
        ("APRN", frozenset(), False),
        ("nurse practitioner", frozenset(), True),  # hardcoded tokens still work
        ("rbac", frozenset({"lead", "data", "engineer"}), False),
        ("", frozenset({"anything"}), False),
    ],
)
def test_is_searchable_title_with_profile_tokens(
    term: str, extra_tokens: frozenset[str], expected: bool
) -> None:
    assert _is_searchable_title(term, extra_tokens=extra_tokens) is expected


def test_profile_tokens_permissive_for_unknown_domain() -> None:
    # A nurse profile hits none of the hardcoded domain tokens, so the
    # user's own keywords/skills are trusted as title vocabulary.
    config = {
        "target_roles": ["Nurse Practitioner"],
        "keyword_searches": ["APRN"],
        "keywords": {"technical": ["phlebotomy"]},
    }
    tokens = _profile_title_tokens(config)
    assert "aprn" in tokens
    assert "phlebotomy" in tokens
    assert "nurse" in tokens


def test_profile_tokens_strict_for_known_tech_domain() -> None:
    # A tech profile hits the hardcoded domain tokens, so skills stay skills.
    config = {
        "target_roles": ["Lead Data Engineer"],
        "keyword_searches": ["rbac", "dbt"],
        "keywords": {"technical": ["apache iceberg"]},
    }
    tokens = _profile_title_tokens(config)
    assert "rbac" not in tokens
    assert "iceberg" not in tokens
    assert "data" in tokens  # role tokens always harvested


# ── REGRESSION: tech profiles behave as before ──────────────────────────────

def test_tech_profile_skill_keywords_still_dropped() -> None:
    config = {
        "target_roles": ["Lead Data Engineer"],
        "keyword_searches": ["rbac", "dbt", "sox compliance", "data platform"],
    }
    terms, _, _ = _build_search_terms(config)
    lowered = _lowered(terms)
    assert "data engineer" in lowered
    assert "data platform" in lowered
    for skill in ("rbac", "dbt", "sox compliance"):
        assert skill not in lowered, f"skill {skill!r} must not be a board query"


def test_tech_profile_title_shaped_resume_skills_merge_but_pure_skills_do_not() -> None:
    config = {
        "target_roles": ["Data Engineer"],
        "keywords": {"technical": ["python", "data warehousing"]},
    }
    terms, _, _ = _build_search_terms(config)
    lowered = _lowered(terms)
    assert "data warehousing" in lowered
    assert "python" not in lowered


def test_dropped_terms_logged_at_info(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.INFO, logger="job_finder.pipeline"):
        assert _is_searchable_title("rbac") is False
    assert any("rbac" in rec.message for rec in caplog.records)
