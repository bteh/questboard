"""Tag scraped startup jobs by their SOURCE when the company is otherwise Unknown.

Most scraped startup jobs were classified company_type "Unknown" because
``classify_company`` only recognizes famous companies or jobs carrying
funding/employee metadata — which scraped jobs lack. But the source is a strong
startup signal: a job from BuiltIn / YC / Greenhouse / Lever / Ashby is almost
certainly a startup. ``classify_company`` now accepts the source's scraper
category and uses it as a last-resort tier (curated lists / funding / employee
heuristics still win).
"""
from __future__ import annotations

from job_finder.company_classifier import classify_company

UNKNOWN_CO = "Zzqx Nonexistent Startup Co"


def test_startup_source_tags_unknown_company():
    assert classify_company(UNKNOWN_CO, source_category="startup") == "Early Startup"


def test_crypto_source_tags_unknown_company():
    assert classify_company(UNKNOWN_CO, source_category="crypto") == "Early Startup"


def test_community_source_tags_unknown_company():
    assert classify_company(UNKNOWN_CO, source_category="community") == "Early Startup"


def test_ats_source_tags_unknown_company():
    assert classify_company(UNKNOWN_CO, source_category="ats") == "Growth Stage"


def test_remote_source_stays_unknown():
    # Remote/general boards (RemoteOK, Himalayas, LinkedIn) are not
    # startup-specific, so they must NOT be promoted.
    assert classify_company(UNKNOWN_CO, source_category="remote") == "Unknown"
    assert classify_company(UNKNOWN_CO, source_category="jobspy") == "Unknown"


def test_no_source_stays_unknown():
    assert classify_company(UNKNOWN_CO) == "Unknown"


def test_known_company_wins_over_source():
    # A famous company stays correctly classified even from an "ats" source.
    assert classify_company("Google", source_category="ats") == "FAANG+"


def test_funding_metadata_wins_over_source():
    # Explicit funding data is stronger than the source heuristic.
    assert (
        classify_company(UNKNOWN_CO, funding_stage="Series E", source_category="ats")
        == "Elite Startup"
    )


def test_registry_categories_match_mapped_sources():
    """The source strings jobs carry must resolve to the categories we map."""
    import job_finder.tools.scrapers  # noqa: F401 — triggers plugin registration
    from job_finder.tools.scrapers._registry import get_registry

    cats = {name: meta.category for name, meta in get_registry().items()}
    assert cats.get("builtin") == "startup"
    assert cats.get("workatastartup") == "startup"
    assert cats.get("greenhouse") == "ats"
    assert cats.get("lever") == "ats"
    assert cats.get("ashby") == "ats"
    assert cats.get("cryptojobslist") == "crypto"
