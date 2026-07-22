"""The board's place filter: narrow to reachable quests, never hide remote.

Rows pass a location= filter when their location text matches, when they
say remote/online/nationwide in any wording, or when the source stated no
place at all (unknown is not "elsewhere"). The search box also matches the
location field, so a typed city finds the sit whose location names it.
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
        ("LA babysitting", "https://x.example/la", "Culver City, CA", "lookafter"),
        ("Kansas trial", "https://x.example/ks", "Lenexa, KS", "body"),
        ("Online study", "https://x.example/rem", "Remote", "think"),
        ("Nationwide bonus", "https://x.example/us", "nationwide", "house"),
        ("Placeless drop", "https://x.example/none", "", "flip"),
    )
    for title, url, location, vertical in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            location=location, vertical=vertical,
        )


VERTS = "lookafter,body,think,house,flip"


def test_place_narrows_but_never_hides_remote_or_placeless(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Culver City"}
    )
    assert resp.status_code == 200, resp.text
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert titles == {"LA babysitting", "Online study", "Nationwide bonus", "Placeless drop"}


def test_place_matching_is_case_insensitive(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS, "location": "lenexa"})
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert "Kansas trial" in titles
    assert "LA babysitting" not in titles


def test_search_box_matches_the_location_field(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS, "search": "Lenexa"})
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert titles == {"Kansas trial"}


def test_no_location_param_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS})
    assert resp.json()["total"] == 5


def test_near_me_only_drops_remote_and_placeless(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # location_strict is the "near me only" toggle: it keeps only rows that
    # actually match the place, dropping the remote/nationwide/placeless
    # escape hatches so the filter visibly bites
    resp = client.get(
        "/api/v1/applications",
        params={"vertical": VERTS, "location": "Culver City", "location_strict": "true"},
    )
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert titles == {"LA babysitting"}


def test_near_me_only_without_a_place_is_a_noop(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # strict with no place has nothing to narrow to: it must not empty the board
    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location_strict": "true"}
    )
    assert resp.json()["total"] == 5


def _seed_states(jf_db) -> None:
    rows = (
        ("Florida-only bonus", "https://x.example/fl", "FL only", "house"),
        ("Northeast bonus", "https://x.example/ne", "ME, VT & NH", "house"),
        ("DC-corridor bonus", "https://x.example/dc", "AL, CT, D.C., MD, VA Only", "house"),
        ("Georgia sit", "https://x.example/gasit", "Atlanta, Georgia", "lookafter"),
        ("Mexico study", "https://x.example/mx", "Guadalajara", "body"),
        # the review's confirmed false-positive traps:
        ("Niagara sit", "https://x.example/niag", "Niagara Falls, NY", "lookafter"),   # not GA
        ("West Virginia bonus", "https://x.example/wv", "Charleston, West Virginia", "house"),  # not VA
        ("Austin prose sit", "https://x.example/atx", "office in Austin, TX", "lookafter"),  # not IN
        ("Slash-list bonus", "https://x.example/slash", "OR/WA only", "house"),  # Oregon+Washington
    )
    for title, url, location, vertical in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            location=location, vertical=vertical,
        )


def test_a_typed_state_name_matches_abbreviation_lists(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Florida"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Florida-only bonus" in titles
    assert "Northeast bonus" not in titles


def test_a_typed_abbreviation_matches_the_full_state_name(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "GA"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Georgia sit" in titles
    # the whole point: "GA" never matches cities that merely contain the
    # letters (Guadalajara, Niagara, Chattanooga) — a query-time SQL
    # tokenizer would have leaked all of these
    assert "Mexico study" not in titles
    assert "Niagara sit" not in titles


def test_virginia_does_not_leak_west_virginia(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Virginia"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    # the DC-corridor bonus lists VA; the West Virginia bonus does not
    assert "DC-corridor bonus" in titles
    assert "West Virginia bonus" not in titles


def test_prose_word_is_never_a_state(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    # "Indiana" (abbr IN) must not return "office in Austin, TX"
    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Indiana"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Austin prose sit" not in titles


def test_slash_separated_availability_matches(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Oregon"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Slash-list bonus" in titles  # "OR/WA only"


def test_a_state_query_still_keeps_remote_and_placeless(api_client) -> None:
    client, jf_db = api_client
    # the seed from the top-of-file _seed(): a Remote study and a placeless drop
    _seed(jf_db)
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Georgia"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    # a place never hides work-from-anywhere or nationwide supply
    assert "Online study" in titles
    assert "Nationwide bonus" in titles
    assert "Placeless drop" in titles


def test_near_me_only_with_a_state_keeps_only_that_state(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": VERTS, "location": "Georgia", "location_strict": "true"},
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Georgia sit" in titles
    # near-me only drops work-from-anywhere and nationwide supply
    assert "Online study" not in titles
    assert "Nationwide bonus" not in titles
    assert "Placeless drop" not in titles


def test_state_tokens_match_inside_availability_lists(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    for query in ("Vermont", "VT"):
        resp = client.get(
            "/api/v1/applications", params={"vertical": VERTS, "location": query}
        )
        titles = {r["job_title"] for r in resp.json()["items"]}
        assert "Northeast bonus" in titles, query
        assert "Florida-only bonus" not in titles, query


def test_dotted_dc_matches_both_ways(api_client) -> None:
    client, jf_db = api_client
    _seed_states(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "DC"}
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "DC-corridor bonus" in titles


def _blank_state_codes(jf_db, url: str) -> None:
    """Simulate a row saved before the state parser shipped: raw location
    text, empty state_codes (the live DB is mostly these)."""
    from sqlalchemy import text as sql_text

    session = jf_db._SessionLocal()
    try:
        session.execute(
            sql_text("UPDATE applications SET state_codes = '' WHERE job_url = :u"),
            {"u": url},
        )
        session.commit()
    finally:
        session.close()


def _seed_unparsed(jf_db) -> None:
    rows = (
        ("San Diego sit", "https://x.example/sd", "San Diego, CA", "lookafter"),
        ("Sacramento study", "https://x.example/sac", "Sacramento, California", "body"),
        ("Charleston WV sit", "https://x.example/chswv", "Charleston, West Virginia", "lookafter"),
    )
    for title, url, location, vertical in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            location=location, vertical=vertical,
        )
        _blank_state_codes(jf_db, url)


def test_state_query_falls_back_to_raw_location_text(api_client) -> None:
    """A typed state must still find rows whose state_codes never got
    parsed: match the raw location against the state's full name and its
    abbreviation (word-boundary style, so no substring noise)."""
    client, jf_db = api_client
    _seed_unparsed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": VERTS, "location": "California", "location_strict": "true"},
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "San Diego sit" in titles       # ", CA" abbreviation, no codes
    assert "Sacramento study" in titles    # spelled-out name, no codes


def test_abbrev_query_falls_back_to_raw_location_text(api_client) -> None:
    client, jf_db = api_client
    _seed_unparsed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": VERTS, "location": "CA", "location_strict": "true"},
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "San Diego sit" in titles
    assert "Sacramento study" in titles


def test_raw_text_fallback_keeps_the_false_positive_guards(api_client) -> None:
    client, jf_db = api_client
    _seed_unparsed(jf_db)
    _seed_states(jf_db)

    # Virginia must not leak West Virginia even with no codes to lean on
    resp = client.get(
        "/api/v1/applications",
        params={"vertical": VERTS, "location": "Virginia", "location_strict": "true"},
    )
    titles = {r["job_title"] for r in resp.json()["items"]}
    assert "Charleston WV sit" not in titles
    assert "West Virginia bonus" not in titles

    # lowercase prose "in" is still never Indiana, and GA still never
    # matches cities that merely contain the letters
    for state, trap in (("Indiana", "Austin prose sit"), ("GA", "Niagara sit")):
        resp = client.get(
            "/api/v1/applications",
            params={"vertical": VERTS, "location": state, "location_strict": "true"},
        )
        titles = {r["job_title"] for r in resp.json()["items"]}
        assert trap not in titles, state
