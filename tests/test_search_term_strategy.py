"""Board search terms should be job TITLES, run title-first.

Two bugs surfaced in the live logs:

1. Skill keywords were searched as job TITLES. The user's keyword_searches
   (rbac, mcp, dbt, "sox compliance", "pii masking", "federated query",
   "semantic layer", "apache iceberg") were merged into the role list and each
   run as a JobSpy job-title query — returning noise/zero and burning the
   board's limited query budget. Skills belong in scoring, not title search.

2. The most important role searches got starved. The query priority ran short
   keywords first and real role titles last, so when a board's circuit breaker
   tripped (LinkedIn 429/CAPTCHA), the role titles ("data engineer", "data
   platform") returned "0 results from no boards".

Fix: ``_is_searchable_title`` keeps only title-shaped terms as board queries,
and ``_search_query_priority`` runs job titles before niche/skill terms.
"""
from __future__ import annotations

import pytest

from job_finder.pipeline import _is_searchable_title, _search_query_priority

# Real role titles + title-shaped domain phrases — should be searched on boards.
SEARCHABLE = [
    "Lead Data Engineer",
    "Head of Data Platform",
    "Director of Analytics Engineering",
    "Data Platform Architect",
    "data engineer",
    "data platform",
    "data mesh",
    "analytics engineering",
    "machine learning engineer",
    "ai platform",
]

# Pure skills / tools / acronyms — must NOT be searched as job titles.
SKILLS = [
    "rbac",
    "mcp",
    "dbt",
    "sox compliance",
    "pii masking",
    "federated query",
    "semantic layer",
    "apache iceberg",
    "trino",
    "starburst",
    "datahub",
    "claude",
    "glean",
]


@pytest.mark.parametrize("term", SEARCHABLE)
def test_titles_are_searchable(term):
    assert _is_searchable_title(term) is True, f"should be searched as a title: {term!r}"


@pytest.mark.parametrize("term", SKILLS)
def test_skills_are_not_searchable(term):
    assert _is_searchable_title(term) is False, f"skill should NOT be a title query: {term!r}"


def test_role_titles_run_before_domain_and_skills():
    spec = {"sql", "python"}
    # role-type title < domain-only phrase < short skill term
    assert _search_query_priority("data engineer", spec) < _search_query_priority("data platform", spec)
    assert _search_query_priority("data platform", spec) < _search_query_priority("sql", spec)
    assert _search_query_priority("Lead Data Engineer", spec) < _search_query_priority("data mesh", spec)


def test_sorting_puts_roles_first():
    spec: set[str] = set()
    terms = ["dbt", "data platform", "Lead Data Engineer", "data mesh", "data engineer"]
    ordered = sorted(terms, key=lambda t: _search_query_priority(t, spec))
    # The two role-type titles must come before the domain-only phrases.
    assert ordered.index("Lead Data Engineer") < ordered.index("data platform")
    assert ordered.index("data engineer") < ordered.index("data mesh")
