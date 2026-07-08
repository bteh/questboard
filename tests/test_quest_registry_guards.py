"""Registry and pipeline guards for quest verticals.

Quest scrapers share the career registry but must never leak into career
machinery: the career pipeline can never enable them (even when user yaml
says enabled: true), the sources endpoint hides them from career job-board
settings, run_scrapers never sweeps them in by default, and
finalize_scraper_jobs never mines pay from a quest description.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.tools.scrapers import get_all_metadata, get_registry, register_scraper  # noqa: E402
from job_finder.tools.scrapers._registry import ScraperMeta, default_scraper_names  # noqa: E402


@pytest.fixture()
def fake_camera_scraper():
    """Register a quest scraper for the duration of one test."""
    name = "fake_1iota_test"

    @register_scraper(
        name=name,
        display_name="Fake 1iota",
        url="https://1iota.example",
        category="camera",
        vertical="camera",
        enabled_by_default=False,
    )
    def _search(**kwargs):
        return []

    yield name
    get_registry().pop(name, None)


def _meta(vertical: str, enabled_by_default: bool = False, search_fn=lambda **k: []):
    return ScraperMeta(
        name="m", display_name="M", url="https://m.example", description="",
        category="test", enabled_by_default=enabled_by_default,
        search_fn=search_fn, vertical=vertical,
    )


def test_quest_scrapers_are_never_enabled_by_default():
    metas = get_all_metadata()
    assert metas, "registry unexpectedly empty"
    career = [m for m in metas if m.vertical == "career"]
    quest = [m for m in metas if m.vertical != "career"]
    assert career, "career scrapers missing from registry"
    assert quest, "quest scrapers expected in the registry"
    assert all(not m.enabled_by_default for m in quest)
    assert all(m.vertical in {"career", "camera", "study", "lens", "party"} for m in metas)


def test_register_scraper_records_vertical(fake_camera_scraper):
    assert get_registry()[fake_camera_scraper].vertical == "camera"


def test_default_scraper_names_exclude_quest_scrapers(fake_camera_scraper):
    names = default_scraper_names()
    assert fake_camera_scraper not in names
    assert "remotive" in names


def test_pipeline_never_enables_quest_scraper_even_when_yaml_says_enabled():
    from job_finder.pipeline import _career_scraper_enabled

    camera = _meta("camera")
    assert _career_scraper_enabled(camera, {"name": "m", "enabled": True}) is False
    assert _career_scraper_enabled(camera, None) is False

    career = _meta("career")
    assert _career_scraper_enabled(career, {"name": "m", "enabled": True}) is True
    assert _career_scraper_enabled(career, {"name": "m", "enabled": False}) is False
    assert _career_scraper_enabled(career, None) is False
    assert _career_scraper_enabled(_meta("career", enabled_by_default=True), None) is True
    # Metadata-only entries (jobspy boards) are never in the plugin set.
    assert (
        _career_scraper_enabled(_meta("career", enabled_by_default=True, search_fn=None), None)
        is False
    )


def test_finalize_never_mines_salary_from_quest_descriptions():
    from job_finder.tools.scrapers._utils import finalize_scraper_jobs

    description = "Compensation: a $50/hour stipend for one 60-minute session."
    career = {"title": "Data Engineer", "company": "Acme", "description": description}
    study = {
        "title": "Paid study: snacking habits",
        "company": "Fieldwork Chicago",
        "description": description,
        "vertical": "study",
    }
    finalize_scraper_jobs([career, study])

    # Control: the same sentence DOES parse on a career row, so the study
    # assertion below proves the gate and not a regex miss.
    assert career["salary_min"] == pytest.approx(50 * 2080)
    assert career["salary_source"] == "parsed_from_description"

    assert study.get("salary_min") is None
    assert study.get("salary_max") is None
    assert study["salary_source"] is None
    # Contract stamping still applies to quest rows.
    assert study["date_confidence"] == "missing"


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORKSPACE_STORAGE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

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

    with TestClient(app_main.app) as client:
        yield client


def test_sources_endpoint_hides_quest_scrapers_by_default(api_client, fake_camera_scraper):
    resp = api_client.get("/api/v1/scrapers/sources")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert fake_camera_scraper not in names
    assert "remotive" in names
    assert all(s["vertical"] == "career" for s in resp.json())


def test_sources_endpoint_widens_on_request(api_client, fake_camera_scraper):
    everything = api_client.get("/api/v1/scrapers/sources", params={"vertical": "all"})
    names = {s["name"] for s in everything.json()}
    assert fake_camera_scraper in names
    assert "remotive" in names

    camera_only = api_client.get(
        "/api/v1/scrapers/sources", params={"vertical": "camera"}
    )
    camera_names = {s["name"] for s in camera_only.json()}
    assert fake_camera_scraper in camera_names
    assert all(get_registry()[n].vertical == "camera" for n in camera_names)
    assert "remotive" not in camera_names
