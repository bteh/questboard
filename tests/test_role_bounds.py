"""role_bounds is the one home of title level/seniority bounds, shared by core and board."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


class CoreNeverImportsBackend(unittest.TestCase):
    def test_no_src_module_imports_backend(self) -> None:
        offenders = []
        for path in (ROOT / "src" / "job_finder").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                if any(n == "backend" or n.startswith("backend.") for n in names):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


class BoardUsesTheSameBounds(unittest.TestCase):
    def test_board_names_are_the_core_helpers(self) -> None:
        from backend.app.services import local_agent_service as las
        from job_finder import role_bounds

        self.assertIs(las.title_level, role_bounds.title_level)
        self.assertIs(las.ic_seniority, role_bounds.ic_seniority)
        self.assertIs(las._title_bound_exclusion, role_bounds.title_bound_exclusion)
        self.assertIs(las._wanted_levels, role_bounds.wanted_levels)
        self.assertIs(las._wanted_ic_seniorities, role_bounds.wanted_ic_seniorities)


class KeptLeveledRolesStayProtected(unittest.TestCase):
    """Oct 29 2026: the leveled roles kept as their own query must survive the task cap."""

    def test_cap_keeps_every_leveled_role_query(self) -> None:
        from job_finder.pipeline import (
            _cap_search_tasks,
            _consolidate_with_provenance,
            _role_derived_terms,
        )

        roles = ["Data Engineering Manager", "Director of Data Engineering",
                 "Lead Data Engineer", "Staff Data Engineer"]
        keywords = ["Snowflake", "Databricks", "data pipeline", "data governance"]
        consolidated, provenance = _consolidate_with_provenance(roles, keywords)
        role_terms = _role_derived_terms(consolidated, roles, provenance)
        for role in ("director of data engineering", "lead data engineer", "staff data engineer"):
            self.assertIn(role, role_terms)

        tasks = [(term, place) for place in ("Seattle", "Remote") for term in consolidated]
        kept = {term.lower() for term, _ in _cap_search_tasks(tasks, 4, role_terms)}
        self.assertTrue(role_terms <= kept)


if __name__ == "__main__":
    unittest.main()
