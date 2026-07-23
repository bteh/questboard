"""Tests for the YC Work at a Startup scraper normalizer.

Regression coverage for the operator-precedence bug that discarded
``companyName`` for every real YC job (the live data-page shape carries
``companyName``/``companySlug`` but no nested ``company`` object), leaving
every workatastartup job with a blank company.
"""

from __future__ import annotations

from job_finder.tools.scrapers.yc_workatastartup import _normalize_json_job


def test_company_name_from_live_yc_shape():
    """The live YC data-page shape uses ``companyName`` and no ``company`` key."""
    item = {
        "title": "Engineering Manager",
        "salary": "$200K - $250K",
        "companyName": "SnapMagic",
        "companySlug": "snapmagic",
        "companyBatch": "S15",
        "url": "/jobs/123",
    }
    result = _normalize_json_job(item)
    assert result["company"] == "SnapMagic"


def test_company_name_snake_case():
    item = {"title": "SWE", "company_name": "Acme", "url": "/jobs/1"}
    assert _normalize_json_job(item)["company"] == "Acme"


def test_company_name_nested_dict_fallback():
    item = {"title": "SWE", "company": {"name": "NestedCo"}, "url": "/jobs/2"}
    assert _normalize_json_job(item)["company"] == "NestedCo"


def test_company_name_plain_string_fallback():
    item = {"title": "SWE", "company": "StringCo", "url": "/jobs/3"}
    assert _normalize_json_job(item)["company"] == "StringCo"


def test_company_name_missing_is_blank_not_crash():
    item = {"title": "SWE", "url": "/jobs/4"}
    assert _normalize_json_job(item)["company"] == ""


def test_string_salary_is_parsed_to_min_max():
    """YC carries a string ``salary`` field, not salary_min/salary_max."""
    item = {
        "title": "Senior Engineer",
        "companyName": "Acme",
        "salary": "$200K - $250K",
        "url": "/jobs/5",
    }
    result = _normalize_json_job(item)
    assert result["salary_min"] == 200000
    assert result["salary_max"] == 250000


# ── 2026-07-22 live shape: no url/job_url keys, only id + login applyUrl ──
#
# The live data-page job object carries ``id`` (the public detail page is
# ``https://www.workatastartup.com/jobs/<id>``, verified 200 unauthenticated)
# and ``applyUrl`` (an account.ycombinator.com/authenticate redirect, login
# gated, never a valid row URL). The scraper was disabled because every row
# landed with an empty URL and got dropped as a dead link; building the URL
# from ``id`` is the fix.

_LIVE_ITEM = {
    "id": "92753",
    "title": "Senior Software Engineer, Email Team",
    "jobType": "Fulltime",
    "location": "United States - Remote / Remote (US)",
    "roleType": "Full stack",
    "salary": "None",
    "companyName": "OneSignal",
    "companySlug": "onesignal",
    "companyBatch": "S11",
    "applyUrl": (
        "https://account.ycombinator.com/authenticate?continue="
        "https%3A%2F%2Fwww.workatastartup.com%2Fapplication_flow%2F92753"
    ),
}


def test_url_built_from_id_for_live_shape():
    result = _normalize_json_job(dict(_LIVE_ITEM))
    assert result["url"] == "https://www.workatastartup.com/jobs/92753"


def test_login_gated_apply_url_is_never_the_row_url():
    result = _normalize_json_job(dict(_LIVE_ITEM))
    assert "authenticate" not in result["url"]


def test_explicit_url_still_wins_over_id():
    item = dict(_LIVE_ITEM)
    item["url"] = "/jobs/555"
    assert _normalize_json_job(item)["url"] == "https://www.workatastartup.com/jobs/555"


def test_string_none_salary_stays_unset():
    """The live shape emits the literal string 'None' for missing salary."""
    result = _normalize_json_job(dict(_LIVE_ITEM))
    assert result["salary_min"] is None
    assert result["salary_max"] is None


def test_scraper_reenabled_now_that_urls_resolve():
    from job_finder.tools.scrapers._registry import get_registry

    meta = get_registry()["workatastartup"]
    assert meta.enabled_by_default is True
