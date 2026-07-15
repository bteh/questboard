"""Remote-scope honesty: a job that is remote only for another country must
not pass a US place filter, and the classifier stays conservative (bare or
ambiguous wording is kept, never guessed into an exclusion)."""

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

from job_finder.remote_scope import classify_remote_scope


@pytest.mark.parametrize(
    "loc",
    [
        "United States",
        "USA",
        "US",
        "Remote - USA",
        "Remote, United States",
        "Remote (US)",
        "REMOTE (US ONLY, LA/SF preferred)",
        "Orlando, United States (Remote)",
        "PA, US",
        "Remote-Friendly, United States",
        # a US state or city parse is a US signal even without 'US' wording
        "San Francisco, California",
        "New York, NY or Remote",
        # mixed lists with a US side stay reachable from the US
        "Canada, United States",
        "Remote (United States | Canada)",
        "United Arab Emirates, United States",
        "Remote, Canada; Remote, US",
    ],
)
def test_us_scoped_wording(loc: str) -> None:
    assert classify_remote_scope(loc) == "us"


@pytest.mark.parametrize("loc", ["Anywhere in the World", "Worldwide", "Global, remote"])
def test_worldwide_wording(loc: str) -> None:
    assert classify_remote_scope(loc) == "worldwide"


@pytest.mark.parametrize(
    "loc",
    [
        "Remote, India",
        "India (Remote)",
        "Hyderabad",
        "Mexico",
        "London",
        "Remote (UK Based only)",
        "REMOTE (EU, Switzerland, Norway)",
        "Remote, Europe",
        "Pangyo (Software Dream Center), South Korea",
        "Hong Kong, Hong Kong, Hong Kong SAR",
        "Costa Rica",
        "Canada",
        "Paris, Remote",
    ],
)
def test_intl_only_wording(loc: str) -> None:
    assert classify_remote_scope(loc) == "intl"


@pytest.mark.parametrize("loc", ["", None, "Remote", "m/w/d", "Only, ", "SF or Remote"])
def test_unknown_wording_never_excludes(loc: str | None) -> None:
    assert classify_remote_scope(loc) != "intl"


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
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(db_path))
    app_main = importlib.import_module("app.main")

    with TestClient(app_main.app) as client:
        yield client, jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def _seed(jf_db) -> None:
    rows = (
        ("US remote role", "https://x.example/us", "Remote, United States", True),
        ("India remote role", "https://x.example/in", "Remote, India", True),
        ("Worldwide role", "https://x.example/ww", "Anywhere in the World", True),
        ("Bare remote role", "https://x.example/rem", "Remote", True),
        ("LA onsite role", "https://x.example/la", "Los Angeles, CA", False),
    )
    for title, url, location, remote in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            location=location, is_remote=remote,
        )


def test_us_place_filter_drops_intl_only_remote(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"location": "California"})
    assert resp.status_code == 200, resp.text
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert "US remote role" in titles
    assert "Worldwide role" in titles
    assert "Bare remote role" in titles
    assert "LA onsite role" in titles
    assert "India remote role" not in titles


def test_typed_intl_place_still_finds_its_own_rows(api_client) -> None:
    # typing the restricted place itself keeps its rows via the place match
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"location": "India"})
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert "India remote role" in titles
