"""A refresh's destructive purges must stay inside the workspace that owns
the preferences driving them.

Bug: the pipeline's location purge passed profile= with no workspace_id, and
both purge functions treated a missing workspace_id as "every workspace with
this profile". Hosted workspaces all share profile="workspace", so a refresh
for workspace X deleted rows belonging to workspace Y. The purges now scope
the way save_application does: an explicit workspace_id owns exactly its
rows; no workspace_id means the legacy NULL-workspace rows for the profile.
"""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture()
def db(tmp_path):
    # Resolve at runtime: other suites reload this module, and a stale
    # collection-time binding would patch a module object the pipeline
    # no longer imports.
    database = importlib.import_module("job_finder.models.database")
    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def _save(db, company, url, *, title="Data Engineer", workspace_id=None):
    return db.save_application(
        job_title=title,
        company=company,
        location="New York, NY",
        job_url=url,
        profile="workspace",
        workspace_id=workspace_id,
    )


def _companies(db):
    return {a.company for a in db.get_all_applications()}


def test_location_purge_without_workspace_id_spares_workspace_rows(db):
    _save(db, "Legacy", "https://example.com/legacy")
    _save(db, "OtherWs", "https://example.com/other", workspace_id="ws-b")

    deleted = db.purge_non_matching_locations(
        preferred_cities=["San Francisco"], profile="workspace",
    )

    assert deleted == 1
    assert _companies(db) == {"OtherWs"}


def test_role_purge_without_workspace_id_spares_workspace_rows(db):
    _save(db, "Legacy", "https://example.com/legacy", title="Barista")
    _save(db, "OtherWs", "https://example.com/other", title="Barista", workspace_id="ws-b")

    deleted = db.purge_non_matching_roles(["data engineer"], profile="workspace")

    assert deleted == 1
    assert _companies(db) == {"OtherWs"}


def test_location_purge_with_workspace_id_stays_inside_that_workspace(db):
    _save(db, "MineStale", "https://example.com/a", workspace_id="ws-a")
    _save(db, "OtherWs", "https://example.com/b", workspace_id="ws-b")
    _save(db, "Legacy", "https://example.com/c")

    deleted = db.purge_non_matching_locations(
        preferred_cities=["San Francisco"], profile="workspace", workspace_id="ws-a",
    )

    assert deleted == 1
    assert _companies(db) == {"OtherWs", "Legacy"}


def test_role_purge_with_workspace_id_stays_inside_that_workspace(db):
    _save(db, "MineStale", "https://example.com/a", title="Barista", workspace_id="ws-a")
    _save(db, "OtherWs", "https://example.com/b", title="Barista", workspace_id="ws-b")
    _save(db, "Legacy", "https://example.com/c", title="Barista")

    deleted = db.purge_non_matching_roles(
        ["data engineer"], profile="workspace", workspace_id="ws-a",
    )

    assert deleted == 1
    assert _companies(db) == {"OtherWs", "Legacy"}


def test_pipeline_location_purge_carries_the_workspace_id(db, monkeypatch):
    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module
    from job_finder.pipeline import JobFinderPipeline

    captured: dict = {}

    def fake_purge(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(db, "purge_non_matching_locations", fake_purge)
    monkeypatch.setattr(pipeline_module, "search_jobs", lambda **_kw: [])
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kw: [])

    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = {
        "job_boards": [],
        "additional_sources": [],
        "search_settings": {"ai_expand_roles": False, "max_days_old": 30},
        "location_preferences": {
            "filter_enabled": True,
            "preferred_cities": ["San Francisco"],
            "include_remote": True,
        },
        "workspace": {"workspace_id": "ws-test"},
    }
    pipeline.search_all_jobs(roles=["Data Engineer"], locations=["San Francisco, CA"])

    assert captured.get("workspace_id") == "ws-test"
