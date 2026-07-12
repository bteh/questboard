"""The application kit: everything prefilled, the human sends it.

Questboard never transmits an application (docs/anti-slop.md; the
2026-07-10 strategy debate, unanimous). These tests pin both halves of
that promise: the kit carries everything a fast, well-prepared human
needs, and no transmit path exists anywhere in the module.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools import auto_apply_tool as kit  # noqa: E402

CONFIG = {
    "applicant_info": {
        "first_name": "Brian",
        "last_name": "T",
        "email": "brian@example.com",
        "phone": "555-0100",
        "linkedin_url": "https://linkedin.com/in/example",
    }
}


class TestNoTransmitPath:
    def test_the_module_cannot_speak_http(self) -> None:
        source = inspect.getsource(kit)
        assert "import requests" not in source
        assert "requests.post" not in source
        assert "urlopen" not in source

    def test_the_old_submit_functions_are_gone(self) -> None:
        assert not hasattr(kit, "submit_greenhouse_application")
        assert not hasattr(kit, "submit_lever_application")
        assert not hasattr(kit, "auto_apply")


class TestKit:
    def test_greenhouse_kit_prefills_the_real_form_fields(self) -> None:
        job = {
            "title": "Platform Engineer",
            "company": "Acme",
            "url": "https://boards.greenhouse.io/acme/jobs/123456",
        }
        result = kit.prepare_application_kit(job, CONFIG, cover_letter_text="Dear team")
        assert result["success"] is True
        assert result["method"] == "greenhouse"
        assert result["apply_url"] == job["url"]
        assert result["fields"]["first_name"] == "Brian"
        assert result["fields"]["email"] == "brian@example.com"
        assert result["fields"]["cover_letter"] == "Dear team"

    def test_lever_kit_uses_lever_field_names(self) -> None:
        job = {
            "title": "Designer",
            "company": "Acme",
            "url": "https://jobs.lever.co/acme/9f8a7b6c-1d2e-3f4a-5b6c-7d8e9f0a1b2c",
        }
        result = kit.prepare_application_kit(job, CONFIG, cover_letter_text="Hello")
        assert result["method"] == "lever"
        assert result["fields"]["name"] == "Brian T"
        assert result["fields"]["urls[LinkedIn]"] == "https://linkedin.com/in/example"
        assert result["fields"]["comments"] == "Hello"

    def test_linkedin_kit_carries_materials_without_a_field_map(self) -> None:
        job = {"title": "PM", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/1"}
        result = kit.prepare_application_kit(job, CONFIG)
        assert result["success"] is True
        assert result["method"] == "linkedin"
        assert result["fields"] == {}
        assert result["application_data"]["first_name"] == "Brian"

    def test_unknown_ats_is_honest(self) -> None:
        job = {"title": "X", "company": "Y", "url": "https://example.com/careers/1"}
        result = kit.prepare_application_kit(job, CONFIG)
        assert result["success"] is False
        assert result["method"] is None

    def test_missing_applicant_info_fails_closed(self) -> None:
        job = {"title": "X", "company": "Y", "url": "https://boards.greenhouse.io/y/jobs/1"}
        result = kit.prepare_application_kit(job, {})
        assert result["success"] is False
        assert "applicant_info" in result["message"]

    def test_missing_resume_never_invents_a_path(self) -> None:
        job = {"title": "X", "company": "Y", "url": "https://boards.greenhouse.io/y/jobs/1"}
        result = kit.prepare_application_kit(job, CONFIG, resume_path="/nope/missing.pdf")
        assert "resume" not in result["fields"]


class TestPipelineStage:
    def test_kits_attach_without_touching_status(self, monkeypatch) -> None:
        from job_finder.pipeline import JobFinderPipeline

        pipeline = JobFinderPipeline.__new__(JobFinderPipeline)
        pipeline.config = {**CONFIG, "auto_apply": {"enabled": True}}

        jobs = [
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "url": "https://boards.greenhouse.io/acme/jobs/123456",
                "recommendation": "STRONG_APPLY",
                "status": "found",
            },
            {
                "title": "Other",
                "company": "B",
                "url": "https://example.com/1",
                "recommendation": "APPLY",
                "status": "found",
            },
        ]
        out = pipeline.prepare_application_kits(jobs)
        assert out[0]["application_kit"]["method"] == "greenhouse"
        assert out[0]["application_kit"]["fields"]["first_name"] == "Brian"
        # the stage prepares; it never marks anything applied
        assert all(j.get("status") == "found" for j in out)
        assert "application_kit" not in out[1]

    def test_disabled_config_prepares_nothing(self) -> None:
        from job_finder.pipeline import JobFinderPipeline

        pipeline = JobFinderPipeline.__new__(JobFinderPipeline)
        pipeline.config = {**CONFIG, "auto_apply": {"enabled": False}}
        jobs = [{
            "title": "X", "company": "Y",
            "url": "https://boards.greenhouse.io/y/jobs/1",
            "recommendation": "STRONG_APPLY",
        }]
        out = pipeline.prepare_application_kits(jobs)
        assert "application_kit" not in out[0]
