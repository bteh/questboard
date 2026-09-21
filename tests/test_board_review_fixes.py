"""Board fixes from the Sep 21 audit: the multi-model review and the data audit.

1. An individual-contributor role carries its seniority. "Staff Data
   Engineer" saved by a manager brought in 249 rows: 100 plain "Data
   Engineer", 15 junior, 50 staff or principal. A role with a seniority word
   admits that seniority and above; a plain role admits every seniority.
2. Many saved roles must not silently drop retrieval groups (the SQL layer
   used to read only the first 20).
3. Each chip row's counts are computed with the other row's selection
   applied, so a chip never promises rows that clicking it hides.
4. CTO, CDO, CIO and "Vice-President" spellings retrieve.
5. The "the person asked for this" mark is consumed on first use.
6. "vice" and "president" are generic title words for the lane check, and
   the SQL layer no longer carries a catch-all "leadership" token.
7. Revenue-operations, GTM, data-protection and insider-risk titles are
   out of a data engineering lane.
8. The level facet has an "ic" bucket for individual-contributor rows.
9. The assistant's verdict tool defines its four tiers.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


def _make_db(tmp_path, monkeypatch, roles: list[str], titles: list[tuple[str, str]]):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(Workspace(id="local", name="Local", slug="local", last_active_at=now, expires_at=now + timedelta(days=7)))
    db.add(WorkspacePreferences(workspace_id="local", roles_json=json.dumps(roles), keywords_json="[]", workplace_preference="remote_friendly", max_days_old=45))
    db.add_all(
        [
            ApplicationRecord(
                job_title=title, company=f"Co {i}", job_url=f"https://jobs.example/{i}",
                location="Los Angeles, CA", state_codes=",CA,", remote_scope="us", is_remote=False,
                source=source, vertical="career", date_posted=now.isoformat(), date_confidence="exact", date_found=now,
            )
            for i, (title, source) in enumerate(titles)
        ]
    )
    db.commit()
    return db, generator


def _visible(db) -> set[str]:
    from app.services import local_agent_service

    return {str(row["title"]) for row in local_agent_service.search_work(db, page_size=50)["results"]}


IC_TITLES = [
    ("Data Engineer", "greenhouse"),
    ("Data Engineer II", "greenhouse"),
    ("Junior Data Engineer", "greenhouse"),
    ("Senior Data Engineer", "greenhouse"),
    ("Staff Data Engineer", "greenhouse"),
    ("Principal Data Engineer", "greenhouse"),
    ("Data Engineering Manager", "greenhouse"),
]


def test_staff_role_admits_staff_and_above_only(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["Staff Data Engineer"], IC_TITLES)
    try:
        visible = _visible(db)
        assert {"Staff Data Engineer", "Principal Data Engineer"} <= visible
        for hidden in ("Data Engineer", "Data Engineer II", "Junior Data Engineer", "Senior Data Engineer", "Data Engineering Manager"):
            assert hidden not in visible, hidden
    finally:
        gen.close()


def test_senior_role_admits_senior_and_above(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["Senior Data Engineer"], IC_TITLES)
    try:
        visible = _visible(db)
        assert {"Senior Data Engineer", "Staff Data Engineer", "Principal Data Engineer"} <= visible
        assert "Data Engineer" not in visible
        assert "Junior Data Engineer" not in visible
    finally:
        gen.close()


def test_plain_role_admits_every_individual_contributor_seniority(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["Data Engineer"], IC_TITLES)
    try:
        visible = _visible(db)
        assert {"Data Engineer", "Junior Data Engineer", "Senior Data Engineer", "Staff Data Engineer", "Principal Data Engineer"} <= visible
        assert "Data Engineering Manager" not in visible
    finally:
        gen.close()


def test_many_saved_roles_keep_every_retrieval_group(tmp_path, monkeypatch) -> None:
    roles = ["Data Engineering Manager", "Data Platform Lead", "Director of Analytics", "Machine Learning Manager", "Database Administrator", "Analytics Engineering Manager"]
    db, gen = _make_db(tmp_path, monkeypatch, roles, [("Database Administrator", "greenhouse"), ("Data Engineering Manager", "greenhouse")])
    try:
        from app.services import local_agent_service as las

        assert len(las._retrieval_token_groups(roles)) > 20, "this case must exceed the old 20-group ceiling"
        visible = _visible(db)
        assert "Database Administrator" in visible
        assert "Data Engineering Manager" in visible
    finally:
        gen.close()


def test_chief_and_vice_president_spellings_retrieve(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["CTO, Data Platform", "Vice-President, Data Engineering"], [("CTO, Data Platform", "greenhouse"), ("Vice-President, Data Engineering", "greenhouse"), ("VP Data Engineering", "greenhouse")])
    try:
        visible = _visible(db)
        assert {"CTO, Data Platform", "Vice-President, Data Engineering", "VP Data Engineering"} <= visible
    finally:
        gen.close()


def _call(db, **overrides):
    from app.api.applications import list_profile_work

    kwargs = dict(
        search=None, location=None, location_strict=False, salary_min=None, salary_max=None, salary_currency=None,
        is_remote=None, founding_only=False, posted_within_days=None, found_within_days=None, timezone_name="UTC",
        source_category=None, level=None, sort_by="date_found", page=1, page_size=24,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="local")), db=db,
    )
    kwargs.update(overrides)
    return list_profile_work(**kwargs)


def test_each_chip_row_counts_with_the_other_selection_applied(tmp_path, monkeypatch) -> None:
    titles = [
        ("Lead Data Engineer", "remotive"), ("Lead Data Engineer", "remotive"),
        ("Data Engineering Manager", "greenhouse"), ("Data Engineering Manager", "greenhouse"), ("Data Engineering Manager", "greenhouse"),
    ]
    db, gen = _make_db(tmp_path, monkeypatch, ["Data Engineering Manager", "Data Engineering Lead"], titles)
    try:
        base = _call(db)
        assert base.levels == {"lead": 2, "manager": 3}
        remote = _call(db, source_category="remote")
        assert remote.total == 2
        assert remote.levels.get("lead") == 2
        assert "manager" not in remote.levels, "Manager 3 would promise rows the Remote shelf hides"
        lead = _call(db, level="lead")
        assert lead.source_categories.get("remote") == 2
        assert "ats" not in lead.source_categories
    finally:
        gen.close()


def test_level_facet_counts_and_filters_individual_contributors(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["Staff Data Engineer", "Data Engineering Manager"], [("Staff Data Engineer", "greenhouse"), ("Principal Data Engineer", "greenhouse"), ("Data Engineering Manager", "greenhouse")])
    try:
        base = _call(db)
        assert base.levels == {"ic": 2, "manager": 1}
        ic = _call(db, level="ic")
        assert {item.job_title for item in ic.items} == {"Staff Data Engineer", "Principal Data Engineer"}
    finally:
        gen.close()


def test_the_request_mark_is_consumed_on_first_use(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.services import agent_run_progress

    agent_run_progress.clear()
    agent_run_progress.mark_requested("propose_roles")
    assert agent_run_progress.consume_requested("propose_roles") is True
    assert agent_run_progress.requested_task() == ""
    assert agent_run_progress.consume_requested("propose_roles") is False


def test_mcp_propose_consumes_the_mark(tmp_path, monkeypatch) -> None:
    db, gen = _make_db(tmp_path, monkeypatch, ["Data Engineering Manager"], [])
    try:
        from app import local_mcp
        from app.services import agent_run_progress, local_agent_service

        seen: list[bool] = []

        def recorder(db_, roles, rationale="", keywords=None, *, requested_by_user=False, **_):
            seen.append(requested_by_user)
            return {"id": 1, "status": "pending", "proposed_roles": roles, "proposed_keywords": []}

        monkeypatch.setattr(local_agent_service, "propose_career_preferences", recorder)
        agent_run_progress.clear()
        agent_run_progress.mark_requested("propose_roles")
        local_mcp.propose_career_preferences(roles=["Data Platform Manager"])
        local_mcp.propose_career_preferences(roles=["Data Platform Manager"])
        assert seen == [True, False]
    finally:
        gen.close()


def test_vice_and_president_are_generic_words_and_leadership_token_is_gone() -> None:
    from app.services import application_service, local_agent_service as las

    assert {"vice", "president"} <= las._ROLE_GENERIC_TOKENS
    assert not las._title_is_in_lane("Vice President, Sales", ["Vice President, Data Engineering"])
    groups = las._retrieval_token_groups(["Data Engineering Manager", "Vice President, Data Engineering"])
    assert not any("leadership" in group for group in groups)
    source = Path(application_service.__file__).read_text(encoding="utf-8")
    assert '"leadership"' not in source


def test_revenue_and_protection_titles_are_out_of_a_data_lane() -> None:
    from app.services import local_agent_service as las

    roles = ["Data Engineering Manager", "Analytics Engineering Lead"]
    for title in ("Revenue Operations Lead", "Manager, GTM Analytics", "Sr. Manager, Data Protection and Insider Risk", "Manager, Revenue Operations"):
        assert not las._title_is_in_lane(title, roles), title
    for title in ("Data Engineering Manager", "Manager, Data & Analytics", "Lead Data Engineer"):
        assert las._title_is_in_lane(title, roles), title


def test_verdict_tool_defines_its_four_tiers() -> None:
    from app import local_mcp
    from app.api.local_agent import _AGENT_TASKS

    doc = (local_mcp.set_work_fit.__doc__ or "").lower()
    for tier in ("strong", "good", "reach", "skip"):
        assert f"{tier}:" in doc or f"{tier} =" in doc, f"{tier} is not defined in the tool description"
    assert "gap" in doc
    prompt = str(_AGENT_TASKS["find_and_rank"]["prompt"]).lower()
    assert "strong" in prompt and "gap" in prompt
