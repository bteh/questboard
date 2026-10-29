"""Oct 29 2026 audit: live in-lane postings that never reached the board.

Each test names the real posting that exposed the bug.
"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for path in (str(ROOT / "backend"), str(ROOT / "src")):
    if path in sys.path:
        sys.path.remove(path)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


HIS_ROLES = [
    "Data Engineering Manager",
    "Senior Data Engineering Manager",
    "Manager, Data Platform",
    "Director of Data Engineering",
    "Analytics Engineering Manager",
    "Manager, Data Products",
    "Engineering Manager, Data Infrastructure",
    "Manager, AI Data Enablement",
    "Lead Data Engineer",
    "Staff Data Engineer",
]


class DesktopWorkerRunScopesRowsToSharedPool(unittest.TestCase):
    """Airbnb "Staff Software Engineer, Marketplaces & Intelligence Data and AI".

    Desktop rows are saved with workspace_id NULL, but the durable worker
    handed the pipeline the real workspace id. Every workspace-scoped lookup
    inside the pull (companies on the board, known URLs, purges) then matched
    zero rows, so board companies lost their cap protection.
    """

    def _run(self, data_workspace_id):
        pipeline_service = importlib.import_module("app.services.pipeline_service")
        captured: dict[str, object] = {}

        class FakePipeline:
            profile_name = "workspace"
            llm = None

            def __init__(self) -> None:
                self.config = {"search_settings": {}, "location_preferences": {}}

            def search_all_jobs(self, **kwargs):
                captured["workspace_id"] = (self.config.get("workspace") or {}).get("workspace_id")
                return []

        run = pipeline_service.PipelineRun(run_id="oct29", profile="workspace", mode="search_only")
        with patch.object(pipeline_service, "get_pipeline", return_value=FakePipeline()), patch.object(
            pipeline_service, "_auto_deduplicate", return_value=0
        ):
            pipeline_service._execute_pipeline(
                run,
                roles=["Staff Data Engineer"],
                locations=["Los Angeles, CA"],
                use_ai=False,
                mode="search_only",
                config_override={"workspace": {"workspace_id": "ws-real"}},
                data_workspace_id=data_workspace_id,
            )
        return captured["workspace_id"]

    def test_desktop_run_scopes_pipeline_to_null_pool(self) -> None:
        self.assertIsNone(self._run(None))

    def test_hosted_run_keeps_visitor_workspace(self) -> None:
        self.assertEqual(self._run("ws-real"), "ws-real")


class RemoteOptionInLocationBeatsOfficeBoilerplate(unittest.TestCase):
    """Pinterest "Principal Engineer, Big Data Platform".

    Location "San Francisco, CA, US; Remote, US" offers a remote option, but
    the description's "In-Office Requirement Statement" boilerplate matched a
    hybrid keyword and the job was dropped as an SF hybrid role.
    """

    DESCRIPTION = (
        "Bachelor's degree in Computer Science, a related technical field, or "
        "equivalent experience. In-Office Requirement Statement: We let the type "
        "of work you do guide the collaboration style. That means we're not "
        "always working in an office, but we continue to gather for key moments."
    )

    def test_listed_remote_option_is_remote(self) -> None:
        from job_finder.company_classifier import classify_work_type

        self.assertEqual(
            classify_work_type("San Francisco, CA, US; Remote, US", self.DESCRIPTION, False),
            "remote",
        )

    def test_hybrid_in_location_still_wins(self) -> None:
        from job_finder.company_classifier import classify_work_type

        self.assertEqual(
            classify_work_type("Remote / Hybrid in San Francisco", self.DESCRIPTION, False),
            "hybrid",
        )

    def test_bare_remote_with_weekly_office_days_stays_hybrid(self) -> None:
        from job_finder.company_classifier import classify_work_type

        self.assertEqual(
            classify_work_type("Remote", "You will work 3 days per week in the office.", True),
            "hybrid",
        )

    def test_single_city_with_office_requirement_stays_hybrid(self) -> None:
        from job_finder.company_classifier import classify_work_type

        self.assertEqual(
            classify_work_type("San Francisco, CA", self.DESCRIPTION, True),
            "hybrid",
        )


class LeveledRolesKeepTheirOwnQuery(unittest.TestCase):
    """Oct 29 run: Indeed and LinkedIn never searched Director of Data
    Engineering, Staff Data Engineer or Lead Data Engineer.

    All three collapsed into the bare query "data engineer", whose plain IC
    results the board's own level and seniority gates reject (551 hidden rows),
    so the saved leveled roles were never asked for by name.
    """

    def test_saved_leveled_roles_are_not_absorbed_into_a_gated_base(self) -> None:
        from job_finder.pipeline import _consolidate_with_provenance

        consolidated, provenance = _consolidate_with_provenance(HIS_ROLES, [])
        for role in ("director of data engineering", "staff data engineer", "lead data engineer"):
            self.assertNotEqual(provenance[role], "data engineer", role)
        self.assertNotIn("data engineer", [term.lower() for term in consolidated])

    def test_plain_saved_role_still_absorbs_its_seniority_variants(self) -> None:
        from job_finder.pipeline import _consolidate_with_provenance

        _consolidated, provenance = _consolidate_with_provenance(
            ["Data Engineer", "Senior Data Engineer", "Staff Data Engineer"], []
        )
        self.assertEqual(provenance["staff data engineer"], provenance["data engineer"])


class StaffingAgencyList(unittest.TestCase):
    """Harnham "Data Engineering Manager" sat on a board with staffing agencies excluded."""

    def test_harnham_is_a_staffing_agency(self) -> None:
        from job_finder.staffing import is_staffing_agency

        self.assertTrue(is_staffing_agency("Harnham"))


if __name__ == "__main__":
    unittest.main()
