"""Tests for multi-format resume ingestion (FIX 3): DOCX/TXT parsing and
scanned-PDF detection on the upload endpoint.
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

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

from job_finder.tools.resume_parser_tool import parse_resume


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _make_blank_pdf_bytes() -> bytes:
    from PyPDF2 import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# parse_resume format dispatch
# ---------------------------------------------------------------------------

def test_parse_resume_extracts_docx_text(tmp_path) -> None:
    path = tmp_path / "sample_resume.docx"
    path.write_bytes(_make_docx_bytes(["Jane Doe", "Senior Nurse Practitioner", "Skills: triage"]))
    text = parse_resume(file_path=str(path))
    assert not text.startswith("ERROR")
    assert "Jane Doe" in text
    assert "Senior Nurse Practitioner" in text


def test_parse_resume_reads_plain_text(tmp_path) -> None:
    path = tmp_path / "sample_resume.txt"
    path.write_text("John Smith\nStaff Engineer\nPython, Kubernetes", encoding="utf-8")
    text = parse_resume(file_path=str(path))
    assert not text.startswith("ERROR")
    assert "Staff Engineer" in text


def test_parse_resume_pdf_still_works_error_free_path(tmp_path) -> None:
    # A blank-page PDF parses without raising; it just yields no text.
    path = tmp_path / "blank_resume.pdf"
    path.write_bytes(_make_blank_pdf_bytes())
    text = parse_resume(file_path=str(path))
    assert text.startswith("WARNING") or len(text.strip()) < 200


def test_find_resume_locates_docx(tmp_path, monkeypatch) -> None:
    from job_finder.tools.resume_parser_tool import find_resume

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "fmtprof_resume.docx").write_bytes(_make_docx_bytes(["hello"]))
    monkeypatch.chdir(tmp_path)
    found = find_resume(profile="fmtprof")
    assert found is not None
    assert found.endswith("fmtprof_resume.docx")


# ---------------------------------------------------------------------------
# Upload endpoint format acceptance + scanned-PDF detection
# ---------------------------------------------------------------------------

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


def test_upload_accepts_docx(client) -> None:
    payload = _make_docx_bytes(["Jane Doe", "Senior Nurse Practitioner"])
    response = client.post(
        "/api/v1/resume/fmtdocx/upload",
        files={
            "file": (
                "resume.docx",
                payload,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parse_status"] == "ok"
    assert body["parse_code"] is None


def test_upload_accepts_txt(client) -> None:
    response = client.post(
        "/api/v1/resume/fmttxt/upload",
        files={"file": ("resume.txt", b"John Smith\nStaff Engineer", "text/plain")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parse_status"] == "ok"
    assert body["parse_code"] is None


def test_upload_rejects_unsupported_extension(client) -> None:
    response = client.post(
        "/api/v1/resume/fmtbad/upload",
        files={"file": ("resume.png", b"\x89PNG fake", "image/png")},
    )
    assert response.status_code == 400


def test_scanned_pdf_sets_parse_code(client) -> None:
    response = client.post(
        "/api/v1/resume/fmtscan/upload",
        files={"file": ("resume.pdf", _make_blank_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parse_status"] == "error"
    assert body["parse_code"] == "SCANNED_PDF"
    # the file is still saved
    status = client.get("/api/v1/resume/fmtscan")
    assert status.status_code == 200
    assert status.json()["exists"] is True
