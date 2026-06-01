"""Regression: the role relevance filter must be domain-aware.

Reproduces a real-world quality bug seen on a data-platform / data-engineering
leadership profile (roles below). Two failure modes existed:

1.  FALSE POSITIVES — balanced + non-remote (place-bound) jobs were matched with
    an ``any_word`` rescue that fired on a single *generic* word shared with the
    role list ("manager", "engineer", "lead", "senior"). That let pure noise
    through: "Partner Marketing Manager", "Service Desk Manager", "Merchandising
    Lead", "Senior Electronics Quality Technician", "Cyber - SAP Security…".

2.  FALSE NEGATIVES — ``all_significant`` required *every* word of some configured
    role to appear in the title, so excellent matches were rejected because no
    configured role was an exact word-subset: "Senior Data Platform Engineer"
    and "Director of Data Platforms & Governance" were dropped even though every
    domain word ("data", "platform") is present.

The fix: match on the role's *domain* words (ignoring generic seniority /
role-type words), with light plural tolerance. A job matches when the domain
words of some role are present in the title; generic-word-only overlap does not.
"""
from __future__ import annotations

import pytest

from job_finder.tools.scrapers._utils import job_passes_role_filter

# Representative data-platform / data-engineering leadership profile.
ROLES = [
    "Lead Data Engineer",
    "Staff Data Engineer",
    "Principal Data Engineer",
    "Senior Manager, Data Engineering",
    "Director of Data Engineering",
    "Head of Data Platform",
    "VP of Data Engineering",
    "Data Platform Architect",
    "AI Platform Engineering Lead",
    "Director of Analytics Engineering",
    "Head of Data Infrastructure",
]


def _passes(title: str, is_remote: bool) -> bool:
    return job_passes_role_filter(
        {"title": title, "is_remote": is_remote},
        ROLES,
        match_mode="all_significant",
        include_founding=True,
        strictness="balanced",
    )


# Off-domain titles that share only generic words with the role list.
NOISE = [
    "Manager, Security Engineering, Identity Access Management",
    "Cyber Identity - PAM/Non Human Identity Senior Consultant",
    "Cyber - SAP Security and GRC Access & Process Control Manager",
    "Partner Marketing Manager",
    "Merchandising Lead NCX",
    "Service Desk Manager",
    "Senior Electronics Quality Technician II",
    "Senior Billing Revenue Analyst",
    "Senior Enterprise Architect",
]

# Genuine data/analytics/platform matches that must survive.
LEGIT_PLACE_BOUND = [
    "Senior Data Engineer",
    "Staff Data Engineer (Scala, Spark, & Gen AI)",
    "Lead Data Engineer",
    "Senior Manager, Data Engineering - Valorant",
    "Director, Data Engineering - League Studios",
    "Senior Analytics Engineer",
    "Data Architect - Power & Utilities - Senior Manager",
]
LEGIT_REMOTE = [
    "Senior Data Platform Engineer",
    "Director of Data Platforms & Governance",  # plural "Platforms"
    "Principal Data Engineer, LLM/AI Platforms (Remote)",
    "Principal Machine Learning & Data Engineer",
    "Head of Data Infrastructure",
]


@pytest.mark.parametrize("title", NOISE)
def test_off_domain_titles_are_rejected_non_remote(title):
    assert _passes(title, is_remote=False) is False, f"noise should be rejected: {title!r}"


@pytest.mark.parametrize("title", NOISE)
def test_off_domain_titles_are_rejected_remote(title):
    assert _passes(title, is_remote=True) is False, f"noise should be rejected: {title!r}"


@pytest.mark.parametrize("title", LEGIT_PLACE_BOUND)
def test_legit_titles_pass_non_remote(title):
    assert _passes(title, is_remote=False) is True, f"legit role should pass: {title!r}"


@pytest.mark.parametrize("title", LEGIT_REMOTE)
def test_legit_titles_pass_remote(title):
    assert _passes(title, is_remote=True) is True, f"legit role should pass: {title!r}"


def test_founding_titles_still_bypass():
    # Founding-role bypass is intentional and must be preserved.
    assert _passes("Founding Engineer", is_remote=True) is True
