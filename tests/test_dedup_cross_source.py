"""Cross-source dedup at ingest: squashed company keys, direct-source wins.

The user's board showed the same opening twice: Alo's "Manager of Data
Engineering" once from the greenhouse watchlist (company "Aloyoga") and once
from LinkedIn (company "ALO"), under different URLs. The old key compared
space-preserving normalized company names, so "alo" never matched "aloyoga".

These tests pin the new behavior:
- company keys are alphanumeric-squashed, with a guarded prefix match
  ("alo" ~ "aloyoga", but two-letter names like "GE" never prefix-match)
- a direct ATS/company source beats an aggregator copy, and the keeper
  borrows pay/dates the loser had
- a shared ATS job token (gh_jid / greenhouse path id) proves sameness even
  when both descriptions are substantial and differ
- non-duplicates survive: same company+title in two cities, and two
  genuinely different roles with similar titles
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.dedup import (
    ats_job_token,
    companies_match,
    company_key,
    title_key,
)
from job_finder.pipeline import _deduplicate

_ALO_DESC = (
    "WHY JOIN ALO? Mindful movement. It's at the core of why we do what we do "
    "at ALO. Because mindful movement in the studio leads to better living. "
    "We are looking for a Manager of Data Engineering to lead our pipelines, "
    "own the lakehouse migration, and grow a team of two engineers."
)

_LONG_A = (
    "Own and scale the data platform end to end: design batch and streaming "
    "pipelines, lead the lakehouse migration, and mentor two engineers on it."
)
_LONG_B = (
    "Build the consumer-facing React dashboard, own the design-system "
    "components, and partner with product on the onboarding redesign work."
)


def _job(title, company, loc, desc, url, source, remote=False, **extra):
    job = {
        "title": title,
        "company": company,
        "location": loc,
        "description": desc,
        "url": url,
        "source": source,
        "is_remote": remote,
    }
    job.update(extra)
    return job


# -- key primitives ----------------------------------------------------------

def test_company_key_squashes_spacing_and_suffixes():
    assert company_key("Alo Yoga") == "aloyoga"
    assert company_key("Aloyoga") == "aloyoga"
    assert company_key("Acme, Inc.") == "acme"


def test_companies_match_guarded_prefix():
    assert companies_match(company_key("ALO"), company_key("Aloyoga"))
    assert companies_match(company_key("EQUANS"), company_key("Equans UK & Ireland"))
    # two-letter names never prefix-match into longer ones
    assert not companies_match(company_key("GE"), company_key("Genentech"))
    assert not companies_match("", "")


def test_title_key_squashes():
    assert title_key("Manager of Data Engineering") == title_key(
        "Manager of Data Engineering "
    )
    assert title_key("Sr. Data Engineer") == title_key("Senior Data Engineer")


def test_ats_job_token_extraction():
    assert ats_job_token(
        "https://www.coinbase.com/careers/positions/8008047?gh_jid=8008047"
    ) == ("greenhouse", "8008047")
    assert ats_job_token(
        "https://boards.greenhouse.io/coinbase/jobs/8008047"
    ) == ("greenhouse", "8008047")
    assert ats_job_token("https://www.linkedin.com/jobs/view/4442198160") is None
    assert ats_job_token("") is None


# -- the Alo case: direct greenhouse vs LinkedIn aggregator ------------------

def test_alo_pair_merges_and_direct_source_wins():
    greenhouse = _job(
        "Manager of Data Engineering", "Aloyoga",
        "Beverly Hills, California, United States",
        _ALO_DESC,
        "https://boards.greenhouse.io/aloyoga/jobs/6119207004?gh_jid=6119207004",
        "greenhouse",
    )
    linkedin = _job(
        "Manager of Data Engineering", "ALO",
        "Beverly Hills, CA",
        _ALO_DESC + " Plus benefits, equity, and an on-site gym for all employees.",
        "https://www.linkedin.com/jobs/view/4442198160",
        "linkedin",
        salary_min=140000, salary_max=180000,
        date_posted="2026-07-17", date_confidence="exact",
    )

    deduped = _deduplicate([greenhouse, linkedin])
    assert len(deduped) == 1
    best = deduped[0]
    # direct ATS source beats the aggregator even though LinkedIn's copy is
    # longer and carries pay
    assert best["source"] == "greenhouse"
    assert "greenhouse.io/aloyoga" in best["url"]
    # ... but the keeper borrows what the loser had and it lacked
    assert best["salary_min"] == 140000
    assert best["salary_max"] == 180000
    assert best["date_posted"] == "2026-07-17"
    assert set(best.get("all_sources", [])) == {"greenhouse", "linkedin"}


def test_recent_aggregator_repost_refreshes_older_direct_ats_copy():
    description = (
        "Lead the data engineering and analytics team, own the warehouse, "
        "governance, BI delivery, and reliable production pipelines."
    )
    builtin = _job(
        "Sr. Manager, Data Engineering & Analytics",
        "Serve Robotics",
        "United States; Toronto, Ontario, Canada",
        description,
        "https://builtin.com/job/sr-manager-data-engineering-analytics/9414145",
        "builtin",
        remote=True,
        date_posted="2026-07-18",
        date_confidence="exact",
        direct_application_url=(
            "https://jobs.ashbyhq.com/serverobotics/"
            "887ef3a7-3bde-4649-820a-a54b0afc4cf9"
        ),
    )
    ashby = _job(
        "Sr. Manager, Data Engineering & Analytics",
        "Serve Robotics",
        "USA (remote); British Columbia (remote); Calgary (remote)",
        description,
        "https://jobs.ashbyhq.com/serverobotics/887ef3a7-3bde-4649-820a-a54b0afc4cf9",
        "ashby",
        remote=True,
        date_posted="2026-05-19T15:32:37Z",
        date_confidence="exact",
    )

    deduped = _deduplicate([builtin, ashby])

    assert len(deduped) == 1
    assert deduped[0]["source"] == "ashby"
    assert deduped[0]["date_posted"] == "2026-07-18"
    assert deduped[0]["direct_application_url"].startswith(
        "https://jobs.ashbyhq.com/serverobotics/"
    )


def test_alo_yoga_spacing_variant_merges():
    jobs = [
        _job("Senior Data Analyst", "Alo Yoga", "Beverly Hills, CA",
             _LONG_A, "u1", "greenhouse"),
        _job("Senior Data Analyst", "Aloyoga", "Beverly Hills, California",
             "", "u2", "linkedin"),
    ]
    assert len(_deduplicate(jobs)) == 1


# -- ATS job token proves sameness across URL shapes -------------------------

def test_shared_greenhouse_job_id_merges_despite_different_descriptions():
    consider = _job(
        "Senior Program Manager, Contracts Analytics", "Coinbase",
        "Remote - USA",
        "Seniority: Senior. Skills: Analytics, Data Extraction, Enablement, "
        "Artificial Intelligence, Contract Review, Program Management, SQL, "
        "stakeholder alignment and quarterly planning for the legal org.",
        "https://www.coinbase.com/careers/positions/8008047?gh_jid=8008047",
        "consider", remote=True,
    )
    getro = _job(
        "Senior Program Manager, Contracts Analytics", "Coinbase",
        "United States, Remote",
        "Seniority: Senior. Skills: Data Extraction, Contract Management, CLM, "
        "Contract Review, Ironclad, Legal Operations, Artificial Intelligence, "
        "vendor management and process automation for contract workflows.",
        "https://boards.greenhouse.io/coinbase/jobs/8008047",
        "getro", remote=True,
    )
    assert len(_deduplicate([consider, getro])) == 1


# -- non-duplicates that must survive ----------------------------------------

def test_same_company_title_in_two_cities_survives():
    jobs = [
        _job("Software Engineer", "Gamma", "Austin, TX", _LONG_A, "u1", "indeed"),
        _job("Software Engineer", "Gamma", "Seattle, WA", _LONG_A, "u2", "linkedin"),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_genuinely_different_roles_with_similar_titles_survive():
    jobs = [
        _job("Manager of Data Engineering", "Acme", "Remote",
             _LONG_A, "u1", "greenhouse", remote=True),
        _job("Manager of Data Science", "Acme", "Remote",
             _LONG_B, "u2", "linkedin", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_short_company_names_never_prefix_merge():
    # "GE" and "Genentech" hiring the same title remotely, one thin
    # description: without the length guard these would wrongly collapse.
    jobs = [
        _job("Data Engineer", "GE", "Remote", _LONG_A, "u1", "indeed", remote=True),
        _job("Data Engineer", "Genentech", "Remote", "", "u2", "linkedin", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_different_substantial_descriptions_same_key_survive():
    # Same squashed key and compatible location, but two clearly different
    # substantial postings and no shared ATS token: keep both.
    jobs = [
        _job("Software Engineer", "Epsilon", "Remote", _LONG_A, "u1",
             "indeed", remote=True),
        _job("Software Engineer", "Epsilon", "Remote", _LONG_B, "u2",
             "linkedin", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 2


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
