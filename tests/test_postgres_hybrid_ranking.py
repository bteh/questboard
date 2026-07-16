"""Real PostgreSQL integration, enabled in CI via TEST_POSTGRES_DATABASE_URL."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, inspect
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

DATABASE_URL = os.getenv("TEST_POSTGRES_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL integration URL not configured")


def test_postgres_hybrid_schema_ordering_and_atomic_ai_cap(monkeypatch):
    from app.models.workspace import UsageCounter, Workspace
    from app.services import application_service, workspace_service
    from job_finder.models.database import ApplicationRecord, JobEmbedding

    engine = create_engine(DATABASE_URL)
    columns = {column["name"] for column in inspect(engine).get_columns("applications")}
    assert {"rank_score", "rank_source", "match_bucket", "match_reasons_json"} <= columns
    assert "job_embeddings" in inspect(engine).get_table_names()

    workspace_id = f"pg-rank-{uuid.uuid4().hex}"
    with Session(engine) as db:
        db.add(Workspace(id=workspace_id, name="Postgres rank test", slug=workspace_id))
        db.add_all(
            [
                ApplicationRecord(
                    workspace_id=workspace_id,
                    job_title="Adjacent but high",
                    company="A",
                    vertical="career",
                    match_bucket="adjacent",
                    rank_score=0.99,
                ),
                ApplicationRecord(
                    workspace_id=workspace_id,
                    job_title="Primary",
                    company="B",
                    vertical="career",
                    match_bucket="primary",
                    rank_score=0.10,
                ),
            ]
        )
        db.commit()

        rows, _total = application_service.get_applications(
            db, workspace_id=workspace_id, sort_by="rank", sort_dir="desc"
        )
        assert [row.job_title for row in rows] == ["Primary", "Adjacent but high"]

        monkeypatch.setenv("HOSTED_MODE", "true")
        monkeypatch.setenv("HOSTED_PLATFORM_MANAGED_AI", "true")
        monkeypatch.setenv("HOSTED_RESUME_ANALYSES_PER_MONTH", "2")
        assert workspace_service._consume_managed_resume_analysis(db, workspace_id) is True
        assert workspace_service._consume_managed_resume_analysis(db, workspace_id) is True
        assert workspace_service._consume_managed_resume_analysis(db, workspace_id) is False

        db.execute(delete(JobEmbedding).where(JobEmbedding.application_id.in_([row.id for row in rows])))
        db.execute(delete(ApplicationRecord).where(ApplicationRecord.workspace_id == workspace_id))
        db.execute(delete(UsageCounter).where(UsageCounter.workspace_id == workspace_id))
        db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        db.commit()
