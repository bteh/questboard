"""Unified watched-companies store.

The Companies tab and the desktop pull must read/write the SAME store: the
workspace ``target_companies`` (names) plus a resolved ats/slug cache. A
company added here has to drive the pull, and a stored exotic token (Workday,
BILL -> billcom) must survive to the scraper without a lossy re-resolution.

Modules from ``app.*`` / ``job_finder.models`` are imported at fixture time,
not at module import: an earlier test (test_workspace_api) purges them from
sys.modules, so a module-level import here would bind a stale generation while
the service's own internal ``from app.services import watchlist_service`` would
resolve the current one — and a patch would miss.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def env():
    from job_finder.models.database import Base
    from job_finder import pipeline as pipeline_mod
    from app.models.workspace import Workspace, WorkspacePreferences
    from app.schemas.workspace import CompanyTarget
    from app.schemas.workspace import WorkspacePreferences as PrefsSchema
    from app.services import watchlist_service, workspace_service

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield SimpleNamespace(
            db=session,
            Workspace=Workspace,
            WorkspacePreferences=WorkspacePreferences,
            CompanyTarget=CompanyTarget,
            PrefsSchema=PrefsSchema,
            watchlist_service=watchlist_service,
            workspace_service=workspace_service,
            watchlist_tokens_by_ats=pipeline_mod.watchlist_tokens_by_ats,
        )
    finally:
        session.close()


def _seed(env, *, companies=None, meta=None) -> str:
    env.db.add(env.Workspace(id="ws1", name="Local", slug="local-ws1"))
    env.db.add(
        env.WorkspacePreferences(
            workspace_id="ws1",
            roles_json=json.dumps(["Data Engineer"]),
            keywords_json="[]",
            target_companies_json=json.dumps(companies or []),
            target_companies_meta_json=json.dumps(meta or []),
        )
    )
    env.db.commit()
    return "ws1"


def _confirmed(name, ats="greenhouse", slug=None, job_count=7):
    return {
        "name": name,
        "slug": slug or name.lower(),
        "ats": ats,
        "job_count": job_count,
        "careers_url": f"https://boards.greenhouse.io/{slug or name.lower()}",
    }


# ── add: resolves + persists ats/slug into the store the pull reads ──────────


def test_add_workspace_company_resolves_and_persists_token(env, monkeypatch):
    wid = _seed(env)
    monkeypatch.setattr(
        env.watchlist_service, "discover_company", lambda name: _confirmed(name, slug="umbra")
    )

    result = env.workspace_service.add_workspace_company(env.db, wid, name="Umbra")

    assert result["companies"] == [
        {"name": "Umbra", "slug": "umbra", "ats": "greenhouse", "job_count": 7,
         "careers_url": "https://boards.greenhouse.io/umbra"}
    ]
    # The NAME is in the store the pull reads, and the resolved token is cached.
    prefs = env.workspace_service.get_workspace_preferences(env.db, wid)
    assert prefs.companies == ["Umbra"]
    assert prefs.company_targets == [
        env.CompanyTarget(name="Umbra", slug="umbra", ats="greenhouse", job_count=7,
                          careers_url="https://boards.greenhouse.io/umbra")
    ]


def test_add_workspace_company_from_pasted_workday_link_keeps_exotic_token(env, monkeypatch):
    wid = _seed(env)

    def _resolve(url, name=""):
        return {"name": name or "Acme", "slug": "acme/careers", "ats": "workday",
                "job_count": 3, "careers_url": "https://acme.wd1.myworkdayjobs.com/careers"}

    monkeypatch.setattr(env.watchlist_service, "resolve_board_url", _resolve)

    env.workspace_service.add_workspace_company(
        env.db, wid, name="Acme", url="https://acme.wd1.myworkdayjobs.com/careers"
    )

    prefs = env.workspace_service.get_workspace_preferences(env.db, wid)
    assert prefs.company_targets[0].ats == "workday"
    assert prefs.company_targets[0].slug == "acme/careers"


# ── the pull config reads the workspace store WITH stored tokens ─────────────


def test_pull_config_carries_stored_tokens_without_re_resolving(env, monkeypatch):
    prefs = env.PrefsSchema(
        roles=["Data Engineer"],
        companies=["BILL"],
        company_targets=[env.CompanyTarget(name="BILL", ats="greenhouse", slug="billcom", job_count=50)],
    )

    def _boom(_names):
        raise AssertionError("confirmed company must not be re-resolved through the catalog")

    monkeypatch.setattr(env.watchlist_service, "build_watchlist_entries", _boom)

    override = env.workspace_service.build_pipeline_config_override(prefs, "ws1")

    assert override["watchlist"] == [
        {"name": "BILL", "ats": "greenhouse", "slug": "billcom", "job_count": 50, "careers_url": ""}
    ]
    # And the pipeline's token grouper trusts the stored slug even with no catalog.
    grouped = env.watchlist_tokens_by_ats(
        override["watchlist"],
        resolve=lambda names: [{"name": n, "ats": "unknown", "slug": ""} for n in names],
    )
    assert grouped == {"greenhouse": ["billcom"]}


def test_pull_config_still_discovers_bare_names_without_meta(env, monkeypatch):
    prefs = env.PrefsSchema(roles=["Data Engineer"], companies=["Anthropic"], company_targets=[])
    monkeypatch.setattr(
        env.watchlist_service,
        "build_watchlist_entries",
        lambda names: [_confirmed(n, slug="anthropic") for n in names],
    )

    override = env.workspace_service.build_pipeline_config_override(prefs, "ws1")

    assert override["watchlist"][0]["slug"] == "anthropic"


# ── delete ───────────────────────────────────────────────────────────────────


def test_remove_workspace_company_drops_name_and_meta(env):
    wid = _seed(
        env,
        companies=["Umbra", "Acme"],
        meta=[_confirmed("Umbra", slug="umbra"), _confirmed("Acme", slug="acme")],
    )

    result = env.workspace_service.remove_workspace_company(env.db, wid, "Umbra")

    assert [c["name"] for c in result["companies"]] == ["Acme"]
    prefs = env.workspace_service.get_workspace_preferences(env.db, wid)
    assert prefs.companies == ["Acme"]
    assert [t.name for t in prefs.company_targets] == ["Acme"]


# ── honest failure ───────────────────────────────────────────────────────────


def test_add_reports_honest_failure_when_no_board_found(env, monkeypatch):
    wid = _seed(env)
    monkeypatch.setattr(
        env.watchlist_service,
        "discover_company",
        lambda name: {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""},
    )

    result = env.workspace_service.add_workspace_company(env.db, wid, name="Umbra")

    assert "Umbra" in result["message"]
    assert "careers" in result["message"].lower()
    # Still stored, honestly marked, so the user can finish it with a link.
    assert result["companies"] == [
        {"name": "Umbra", "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}
    ]


# ── GET migration: legacy bare names surface resolved, and are preserved ──────


def test_get_companies_resolves_and_preserves_legacy_names(env, monkeypatch):
    # The user's existing ["Alo Yoga","BILL"] were saved as bare names, no meta.
    wid = _seed(env, companies=["Alo Yoga", "BILL"])
    resolved = {
        "Alo Yoga": _confirmed("Alo Yoga", slug="aloyoga"),
        "BILL": {"name": "BILL", "slug": "billcom", "ats": "greenhouse", "job_count": 50,
                 "careers_url": "https://boards.greenhouse.io/billcom"},
    }
    monkeypatch.setattr(env.watchlist_service, "discover_company", lambda name: resolved[name])

    result = env.workspace_service.get_workspace_companies(env.db, wid)

    names = [c["name"] for c in result["companies"]]
    assert names == ["Alo Yoga", "BILL"]  # nothing lost
    by_name = {c["name"]: c for c in result["companies"]}
    assert by_name["Alo Yoga"]["ats"] == "greenhouse"
    assert by_name["BILL"]["slug"] == "billcom"
    # Resolution is cached so a second read does not re-discover.
    monkeypatch.setattr(
        env.watchlist_service,
        "discover_company",
        lambda name: (_ for _ in ()).throw(AssertionError("should be cached")),
    )
    again = env.workspace_service.get_workspace_companies(env.db, wid)
    assert {c["name"]: c["slug"] for c in again["companies"]} == {"Alo Yoga": "aloyoga", "BILL": "billcom"}


def test_saving_prefs_preserves_company_meta(env):
    # MCP set_career_preferences / SearchPrefs save must not wipe the cache.
    wid = _seed(env, companies=["BILL"], meta=[
        {"name": "BILL", "slug": "billcom", "ats": "greenhouse", "job_count": 50, "careers_url": ""}
    ])
    prefs = env.workspace_service.get_workspace_preferences(env.db, wid)

    env.workspace_service.save_workspace_preferences(
        env.db, wid, prefs.model_copy(update={"roles": ["Staff Data Engineer"]})
    )

    after = env.workspace_service.get_workspace_preferences(env.db, wid)
    assert after.roles == ["Staff Data Engineer"]
    assert after.companies == ["BILL"]
    assert after.company_targets[0].slug == "billcom"
