"""Tests for resume upload analysis status reporting (FIX 4).

The upload response must say whether analysis ran ('completed'), was skipped
because no LLM is configured ('skipped_no_llm'), or failed ('failed') — and
include the analysis summary when it ran.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

RESUME_TEXT = "Jane Doe — Senior Nurse Practitioner. " * 20  # comfortably > 200 chars

ANALYSIS_FIXTURE = {
    "industry": "healthcare",
    "seniority": "senior",
    "current_title": "Nurse Practitioner",
    "years_experience": 8,
    "skills": ["Patient Care", "Triage"],
    "leadership_signals": ["charge nurse"],
    "suggested_target_roles": ["Nurse Practitioner", "Lead NP"],
    "suggested_keywords": ["primary care", "urgent care"],
    "certifications": ["RN", "FNP-C"],
    "education": [{"degree": "BSN", "field": "Nursing", "institution": "UCLA"}],
    "high_comp_keywords": ["sign-on bonus"],
    "company_tier_signals": ["Mayo Clinic"],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORKSPACE_STORAGE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for var in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)

    for module_name in list(sys.modules):
        if (
            module_name == "app"
            or module_name.startswith("app.")
            or module_name == "job_finder.models"
            or module_name.startswith("job_finder.models.")
        ):
            sys.modules.pop(module_name, None)

    backend_db = importlib.import_module("app.models.database")
    backend_db.init_db(str(db_path))
    app_main = importlib.import_module("app.main")

    resume_service = importlib.import_module("app.services.resume_service")
    monkeypatch.setattr(resume_service, "_KNOWLEDGE_DIR", str(tmp_path / "knowledge"))

    with TestClient(app_main.app) as test_client:
        yield test_client


def _upload(client, profile: str):
    return client.post(
        f"/api/v1/resume/{profile}/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 mock", "application/pdf")},
    )


def test_upload_without_llm_reports_skipped(client) -> None:
    with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value=RESUME_TEXT), patch(
        "app.dependencies.get_llm",
        return_value=SimpleNamespace(is_configured=False),
    ):
        response = _upload(client, "statusnollm")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_status"] == "skipped_no_llm"
    assert body["analysis"] is None
    assert body["parse_status"] == "ok"


def test_upload_with_llm_reports_completed_with_summary(client) -> None:
    with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value=RESUME_TEXT), patch(
        "app.dependencies.get_llm",
        return_value=SimpleNamespace(is_configured=True),
    ), patch(
        "app.services.resume_analyzer.analyze_resume",
        return_value=dict(ANALYSIS_FIXTURE),
    ), patch(
        "app.services.resume_analyzer.persist_analysis_to_profile",
        return_value={},
    ):
        response = _upload(client, "statusok")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_status"] == "completed"
    summary = body["analysis"]
    assert summary is not None
    assert summary["skills"] == ANALYSIS_FIXTURE["skills"]
    assert summary["suggested_target_roles"] == ANALYSIS_FIXTURE["suggested_target_roles"]
    assert summary["suggested_keywords"] == ANALYSIS_FIXTURE["suggested_keywords"]
    assert summary["current_title"] == "Nurse Practitioner"
    assert summary["seniority"] == "senior"
    assert summary["certifications"] == ["RN", "FNP-C"]
    assert summary["education"] == [{"degree": "BSN", "field": "Nursing", "institution": "UCLA"}]


def test_upload_with_llm_failure_reports_failed(client) -> None:
    with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value=RESUME_TEXT), patch(
        "app.dependencies.get_llm",
        return_value=SimpleNamespace(is_configured=True),
    ), patch(
        "app.services.resume_analyzer.analyze_resume",
        return_value=None,
    ):
        response = _upload(client, "statusfail")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_status"] == "failed"
    assert body["analysis"] is None
