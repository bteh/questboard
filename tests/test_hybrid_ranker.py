from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from job_finder.hybrid_ranker import bm25_scores, rank_jobs
from job_finder.models import database


@pytest.fixture()
def db(tmp_path):
    database.init_db(os.path.join(str(tmp_path), "rank.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def _config() -> dict:
    return {
        "target_roles": ["Data Engineering Manager"],
        "keyword_searches": ["data platform", "snowflake", "dbt"],
        "watchlist": [{"name": "Acme"}],
        "location_preferences": {"workplace_preference": "remote_friendly"},
        "compensation": {"min_base": 150_000},
    }


def test_bm25_is_database_independent_and_prefers_intent_terms():
    scores = bm25_scores(
        "data engineering manager snowflake",
        ["data engineering manager snowflake platform", "consumer product marketing"],
    )
    assert scores[0] > scores[1]


def test_lexical_fallback_orders_jobs_and_emits_reasons_without_percentage():
    jobs = [
        {
            "title": "Product Marketing Manager",
            "company": "Other",
            "description": "consumer campaigns",
            "match_bucket": "adjacent",
            "db_id": 2,
        },
        {
            "title": "Data Engineering Manager",
            "company": "Acme",
            "description": "Lead a Snowflake and dbt data platform",
            "is_remote": True,
            "salary_max": 190_000,
            "match_bucket": "primary",
            "db_id": 1,
        },
    ]
    ranked = rank_jobs(jobs, query_text="data engineering manager snowflake dbt", config=_config())
    assert [job["db_id"] for job in ranked] == [1, 2]
    assert ranked[0]["rank_source"] == "lexical"
    assert ranked[0]["match_bucket"] == "primary"
    assert any(reason["code"] == "target_role" for reason in ranked[0]["match_reasons"])
    assert all("%" not in reason["label"] for reason in ranked[0]["match_reasons"])


def test_semantic_component_upgrades_provenance_and_breaks_an_equal_text_tie():
    jobs = [
        {"title": "Data Engineering Manager", "company": "One", "description": "platform", "db_id": 1},
        {"title": "Data Engineering Manager", "company": "Two", "description": "platform", "db_id": 2},
    ]
    ranked = rank_jobs(
        jobs,
        query_text="data engineering manager",
        config=_config(),
        semantic_scores={1: 0.1, 2: 0.9},
    )
    assert [job["db_id"] for job in ranked] == [2, 1]
    assert all(job["rank_source"] == "hybrid" for job in ranked)


def test_primary_bucket_always_precedes_higher_scoring_adjacent_result():
    jobs = [
        {"title": "Data Engineer", "company": "A", "description": "", "db_id": 1, "match_bucket": "primary"},
        {"title": "Data Engineering Manager", "company": "Acme", "description": "snowflake dbt data platform", "db_id": 2, "match_bucket": "adjacent"},
    ]
    ranked = rank_jobs(jobs, query_text="snowflake dbt data platform", config=_config())
    assert [job["match_bucket"] for job in ranked] == ["primary", "adjacent"]


def test_api_exposes_reasons_and_provenance_but_not_raw_rank_score(db):
    rec = db.save_application(
        job_title="Data Engineering Manager",
        company="Acme",
        job_url="https://example.com/1",
        rank_score=0.01234,
        rank_source="hybrid",
        match_bucket="primary",
        match_reasons=[{"code": "target_role", "label": "Title matches Data Engineering Manager"}],
    )
    from app.api.applications import _to_response

    payload = _to_response(rec).model_dump()
    assert payload["rank_source"] == "hybrid"
    assert payload["match_bucket"] == "primary"
    assert payload["match_reasons"][0]["code"] == "target_role"
    assert "rank_score" not in payload
