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
