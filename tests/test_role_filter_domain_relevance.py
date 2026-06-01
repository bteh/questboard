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


# ---------------------------------------------------------------------------
# Off-family ("different job-family") guard.
#
# A few off-domain titles still slipped through mid-rank because several roles
# reduce to a single shared domain word ("data", "analytics", "ai platform"):
# a SALES role matched on "data", a DESIGNER on "ai platform", a FINANCE
# function on "analytics". The guard rejects titles that carry a distinct
# job-family signal word (sales, designer, marketing, security, finance, …)
# that the user's own roles do NOT contain — so it's self-adjusting per
# profession, not hardcoded against any one family.
# ---------------------------------------------------------------------------

# Titles from a DIFFERENT job family — must be rejected for a data-platform
# profile regardless of remote flag.
OFF_FAMILY_NOISE = [
    "Lead Data Center/Hyperscale Sales Development",      # SALES (matches "data")
    "Senior Product Designer, AI Platform",               # DESIGNER (matches "ai platform")
    "Finance Analytics Manager (Product & Engineering)",  # FINANCE function (matches "analytics")
    "Senior Marketing Data Analyst",                      # MARKETING (matches "data")
    "Senior Security Engineer, Data Protection",          # SECURITY (matches "data")
]

# Genuine data/platform/infra roles that must NOT be over-rejected by the guard.
GUARD_SAFE = [
    "Staff Solutions Architect - Data Infrastructure",
    "Staff Data Analyst, GTM",
    "Revenue Analytics Lead",                  # 'revenue' is NOT an off-family word
    "Business Intelligence and Data Analytics Manager",
    "Senior Data Platform Engineer",
    "Director of Data Platforms & Governance",  # 'governance' is NOT off-family
    "Lead Data Engineer",
    "Senior Analytics Engineer",
    "Member of Technical Staff, Financial Infrastructure",  # 'financial' != 'finance'
]


@pytest.mark.parametrize("title", OFF_FAMILY_NOISE)
def test_off_family_titles_are_rejected_non_remote(title):
    assert _passes(title, is_remote=False) is False, f"off-family should be rejected: {title!r}"


@pytest.mark.parametrize("title", OFF_FAMILY_NOISE)
def test_off_family_titles_are_rejected_remote(title):
    assert _passes(title, is_remote=True) is False, f"off-family should be rejected: {title!r}"


@pytest.mark.parametrize("title", GUARD_SAFE)
def test_guard_does_not_over_reject_non_remote(title):
    assert _passes(title, is_remote=False) is True, f"on-family role should pass: {title!r}"


@pytest.mark.parametrize("title", GUARD_SAFE)
def test_guard_does_not_over_reject_remote(title):
    assert _passes(title, is_remote=True) is True, f"on-family role should pass: {title!r}"


def test_off_family_guard_is_self_adjusting_for_a_sales_user():
    """A sales/account-management user's own off-family words must NOT fire.

    Proves the guard is self-adjusting: because 'sales'/'account' appear in
    THESE roles, the off-family set drops them, and genuine sales titles pass.
    """
    sales_roles = ["Sales Engineer", "Account Executive"]

    def _passes_sales(title: str, is_remote: bool) -> bool:
        return job_passes_role_filter(
            {"title": title, "is_remote": is_remote},
            sales_roles,
            match_mode="all_significant",
            include_founding=True,
            strictness="balanced",
        )

    for remote in (True, False):
        assert _passes_sales("Senior Sales Engineer", remote) is True
        assert _passes_sales("Account Executive, Enterprise", remote) is True
