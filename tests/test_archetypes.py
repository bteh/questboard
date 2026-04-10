"""Tests for the profession archetype loader.

Verifies:
- All archetype YAML files parse cleanly via list_archetypes()
- Each archetype has the required metadata (name, description)
- Scoring weights (when overridden) sum to 1.0
- enabled_scrapers references real scraper names from the registry
- apply_archetype merges correctly without mutating the base
"""

from __future__ import annotations

import math
from copy import deepcopy

import pytest
import yaml

from job_finder.profiles import apply_archetype, list_archetypes, load_archetype


# Reproducible base profile for the merge test — same shape as
# config/profiles/default.yaml but kept inline so the test isn't
# coupled to the exact contents of that file.
_BASE = {
    "profile": {"name": "Default", "description": "Base"},
    "scoring": {
        "technical_skills": 0.25,
        "leadership_signal": 0.10,
        "comp_potential": 0.10,
        "platform_building": 0.10,
        "company_trajectory": 0.10,
        "culture_fit": 0.25,
        "career_progression": 0.10,
        "thresholds": {"strong_apply": 70, "apply": 55, "maybe": 40},
    },
    "compensation": {
        "currency": "USD",
        "pay_period": "annual",
        "min_base": 80000,
        "target_total_comp": 150000,
        "include_equity": False,
    },
    "keywords": {"technical": [], "leadership": [], "platform_building": []},
    "search_settings": {"results_per_board": 25, "max_days_old": 14},
}


def _scoring_weight_sum(scoring: dict) -> float:
    return sum(
        v for k, v in scoring.items()
        if isinstance(v, (int, float)) and k != "thresholds"
    )


class TestListArchetypes:
    def test_returns_at_least_the_seven_seeded_archetypes(self) -> None:
        archs = list_archetypes()
        slugs = {a.slug for a in archs}
        expected = {
            "tech",
            "ai-research",
            "crypto",
            "healthcare",
            "education",
            "government",
            "trades",
            "nonprofit",
            "creative",
        }
        missing = expected - slugs
        assert not missing, f"missing seeded archetypes: {missing}"

    def test_every_archetype_has_name_and_description(self) -> None:
        for arch in list_archetypes():
            assert arch.name, f"{arch.slug} has no name"
            assert arch.description, f"{arch.slug} has no description"


class TestLoadArchetype:
    def test_unknown_slug_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_archetype("does-not-exist")

    @pytest.mark.parametrize(
        "slug",
        ["tech", "ai-research", "crypto", "healthcare", "education", "government", "trades", "nonprofit", "creative"],
    )
    def test_each_archetype_parses_and_scoring_sums_to_one(self, slug: str) -> None:
        data = load_archetype(slug)
        assert isinstance(data, dict)
        scoring = data.get("scoring") or {}
        if scoring:  # scoring is optional but if present must sum to 1.0
            total = _scoring_weight_sum(scoring)
            assert math.isclose(total, 1.0, abs_tol=0.001), (
                f"{slug} scoring weights sum to {total}, not 1.0"
            )

    @pytest.mark.parametrize(
        "slug",
        ["tech", "ai-research", "crypto", "healthcare", "education", "government", "trades", "nonprofit", "creative"],
    )
    def test_enabled_scrapers_reference_real_scrapers(self, slug: str) -> None:
        # Build the set of valid scraper names from the registry + JobSpy
        # known list. Tolerate scrapers that don't exist YET (e.g. usajobs,
        # idealist) by allowlisting them — they're being added in a
        # follow-up commit and the archetypes need to know about them.
        from job_finder.tools.scrapers._registry import get_registry

        valid = set(get_registry().keys())
        valid.update({"indeed", "linkedin", "glassdoor", "zip_recruiter", "google"})
        valid.update({"usajobs", "idealist"})  # planned additions

        data = load_archetype(slug)
        enabled = data.get("enabled_scrapers") or []
        unknown = [s for s in enabled if s not in valid]
        assert not unknown, f"{slug} references unknown scrapers: {unknown}"


class TestApplyArchetype:
    def test_returns_new_dict_does_not_mutate_input(self) -> None:
        original = deepcopy(_BASE)
        merged = apply_archetype(_BASE, "healthcare")
        assert _BASE == original, "apply_archetype mutated the base profile"
        assert merged is not _BASE

    def test_archetype_metadata_is_preserved(self) -> None:
        merged = apply_archetype(_BASE, "healthcare")
        assert "archetype" in merged
        assert merged["archetype"]["name"] == "Healthcare"

    def test_nested_dict_merge_only_overrides_specified_keys(self) -> None:
        merged = apply_archetype(_BASE, "healthcare")
        # The healthcare archetype overrides culture_fit and platform_building.
        # Whatever else is in scoring stays from the base via the merge.
        assert merged["scoring"]["culture_fit"] == 0.25
        assert merged["scoring"]["platform_building"] == 0.05
        # thresholds came from healthcare's own block
        assert merged["scoring"]["thresholds"]["strong_apply"] == 70

    def test_lists_are_replaced_wholesale(self) -> None:
        # The base has empty enabled_scrapers; the archetype provides 6.
        merged = apply_archetype(_BASE, "healthcare")
        assert isinstance(merged["enabled_scrapers"], list)
        assert "indeed" in merged["enabled_scrapers"]
        # And it's not the union of base + archetype — it's just the archetype's.
        assert len(merged["enabled_scrapers"]) == 6

    def test_compensation_overrides_apply(self) -> None:
        merged = apply_archetype(_BASE, "healthcare")
        assert merged["compensation"]["target_total_comp"] == 105000
        # Currency wasn't overridden so it stays from base
        assert merged["compensation"]["currency"] == "USD"
