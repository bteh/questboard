"""A title that names the data pipelines team is a data title.

Nov 12 2026: Supabase posted "Engineering Manager - Pipelines" (a change data
capture team: Postgres replication into Snowflake, BigQuery, ClickHouse).
Brian's saved roles all say "data", the title does not, so the pull dropped
it on every strictness and he found it by hand. CI/CD, build and sales
pipelines are not data work and must stay out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

ROLES = [
    "Data Engineering Manager",
    "Senior Data Engineering Manager",
    "Manager, Data Platform",
    "Director of Data Engineering",
    "Engineering Manager, Data Infrastructure",
    "Lead Data Engineer",
    "Staff Data Engineer",
]
SUPABASE = "Engineering Manager - Pipelines"
NOT_DATA = [
    "Engineering Manager, CI/CD Pipelines",
    "Engineering Manager, Build Pipelines",
    "Engineering Manager - Release Pipelines",
    "Sales Pipeline Manager",
]


@pytest.mark.parametrize("strictness", ["loose", "balanced", "strict"])
def test_pull_keeps_the_supabase_pipelines_manager(strictness) -> None:
    from job_finder.tools.scrapers._utils import job_passes_role_filter

    job = {"title": SUPABASE, "is_remote": True, "location": "Remote, Global"}
    assert job_passes_role_filter(job, ROLES, strictness=strictness)


@pytest.mark.parametrize("title", NOT_DATA)
def test_pull_drops_pipelines_that_are_not_data(title) -> None:
    from job_finder.tools.scrapers._utils import job_passes_role_filter

    assert not job_passes_role_filter({"title": title, "is_remote": True}, ROLES)


def test_board_lane_check_agrees_with_the_pull() -> None:
    from app.services.local_agent_service import _title_is_in_lane

    assert _title_is_in_lane(SUPABASE, ROLES)
    for title in NOT_DATA:
        assert not _title_is_in_lane(title, ROLES), title
