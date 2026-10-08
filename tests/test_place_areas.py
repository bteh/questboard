"""Named areas: the San Gabriel Valley (626) and North Orange County.

Owner request, Oct 8 2026, for his brother's IT / analyst and part-time
search: "look in 626 area like arcadia, alhambra, monterey park, el monte.
Also fullerton and those cities." One module (job_finder.place_areas) holds
every area table; the board filter, the Find Work JobSpy fan-out, the
post-search location gate, and the part-time source all read it.
"""

from __future__ import annotations

import ast
import itertools
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from app.services.application_service import place_filter  # noqa: E402
from job_finder import place_areas  # noqa: E402
from job_finder.company_classifier import location_matches_preferences  # noqa: E402
from job_finder.models.database import ApplicationRecord, Base  # noqa: E402
from job_finder.place_areas import (  # noqa: E402
    NORTH_ORANGE_COUNTY,
    SAN_GABRIEL_VALLEY,
    location_in_area,
    search_places,
)
from job_finder.pipeline import (  # noqa: E402
    JobFinderPipeline,
    _BoardPlaceBudget,
    _cap_search_tasks,
    _place_major_search_tasks,
)

SGV = "San Gabriel Valley (626)"
NOC = "North Orange County"

SGV_CITIES = [
    "Arcadia", "Alhambra", "Monterey Park", "El Monte", "South El Monte", "San Gabriel",
    "Rosemead", "Temple City", "San Marino", "South Pasadena", "Pasadena", "Monrovia",
    "Duarte", "Azusa", "Covina", "West Covina", "Baldwin Park", "Irwindale",
    "City of Industry", "Rowland Heights", "Hacienda Heights", "Walnut", "Diamond Bar",
    "La Puente", "Glendora", "Sierra Madre", "Altadena",
]
NOC_CITIES = [
    "Fullerton", "Anaheim", "Brea", "Buena Park", "La Habra", "Placentia", "Yorba Linda",
    "Orange", "Cypress", "La Palma", "Garden Grove", "Stanton",
]


# --------------------------------------------------------------------------- #
# The module itself
# --------------------------------------------------------------------------- #

def test_place_areas_is_pure() -> None:
    """Backend and pipeline both import it, so it may import only stdlib."""
    tree = ast.parse((ROOT / "src/job_finder/place_areas.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "re", "dataclasses"}, imported


def test_metro_tables_left_application_service() -> None:
    text = (ROOT / "backend/app/services/application_service.py").read_text()
    assert "_METRO_CITIES" not in text and "beverly hills" not in text


def test_every_listed_city_is_in_its_area() -> None:
    for city in SGV_CITIES:
        assert city.lower() in SAN_GABRIEL_VALLEY.word_cities, city
    for city in NOC_CITIES:
        assert city.lower() in NORTH_ORANGE_COUNTY.word_cities, city


@pytest.mark.parametrize("typed", [SGV, "626", "SGV", "san gabriel valley", "San Gabriel Valley, CA"])
def test_sgv_aliases_resolve(typed: str) -> None:
    assert place_areas.named_area_for(typed) is SAN_GABRIEL_VALLEY


@pytest.mark.parametrize("typed", [NOC, "North OC", "Fullerton area", "north orange county"])
def test_north_oc_aliases_resolve(typed: str) -> None:
    assert place_areas.named_area_for(typed) is NORTH_ORANGE_COUNTY


@pytest.mark.parametrize("typed", ["Orange County", "Fullerton, CA", "San Gabriel, CA", "Los Angeles"])
def test_plain_places_are_not_named_areas(typed: str) -> None:
    assert place_areas.named_area_for(typed) is None


# --------------------------------------------------------------------------- #
# Look-alike guards, each named for the place that motivated it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("area", "location"),
    [
        (NORTH_ORANGE_COUNTY, "Orange, NJ"),
        (NORTH_ORANGE_COUNTY, "Orange County Choppers, Newburgh, NY"),
        (NORTH_ORANGE_COUNTY, "Orange County, CA"),
        (NORTH_ORANGE_COUNTY, "Orange Cove, CA"),
        (NORTH_ORANGE_COUNTY, "Cypress, TX"),
        (NORTH_ORANGE_COUNTY, "Stanton, TX"),
        (NORTH_ORANGE_COUNTY, "La Brea, Los Angeles, CA"),
        (NORTH_ORANGE_COUNTY, "Brea, PA"),
        (NORTH_ORANGE_COUNTY, "La Habra Heights, CA"),
        (NORTH_ORANGE_COUNTY, "Irvine, CA"),
        (SAN_GABRIEL_VALLEY, "Walnut Creek, CA"),
        (SAN_GABRIEL_VALLEY, "Walnut, MS"),
        (SAN_GABRIEL_VALLEY, "Industry, PA"),
        (SAN_GABRIEL_VALLEY, "Pasadena, TX"),
        (SAN_GABRIEL_VALLEY, "Duarte, PR"),
        (SAN_GABRIEL_VALLEY, "Glendora, NJ"),
        (SAN_GABRIEL_VALLEY, "San Marino, San Marino"),
        (SAN_GABRIEL_VALLEY, "Arcadia, FL"),
        (SAN_GABRIEL_VALLEY, "Santa Monica, CA"),
        (SAN_GABRIEL_VALLEY, "Monterey, CA"),
    ],
)
def test_area_rejects_look_alikes(area, location: str) -> None:
    assert not location_in_area(location, area)


@pytest.mark.parametrize(
    ("area", "location"),
    [(SAN_GABRIEL_VALLEY, f"{c}, CA") for c in SGV_CITIES]
    + [(SAN_GABRIEL_VALLEY, "Arcadia, California, United States"),
       (SAN_GABRIEL_VALLEY, "Industry, CA 91748"),
       (SAN_GABRIEL_VALLEY, "San Gabriel Valley, CA")]
    + [(NORTH_ORANGE_COUNTY, f"{c}, CA") for c in NOC_CITIES]
    + [(NORTH_ORANGE_COUNTY, "Anaheim, Orange County, CA")],
)
def test_area_accepts_its_cities(area, location: str) -> None:
    assert location_in_area(location, area)


@pytest.mark.parametrize(
    ("picked", "inside", "look_alike"),
    [
        ("Covina, CA", "Covina, CA", "West Covina, CA"),
        ("San Gabriel, CA", "San Gabriel, CA", "San Gabriel Valley, CA"),
        ("Pasadena, CA", "Pasadena, CA", "South Pasadena, CA"),
        ("El Monte, CA", "El Monte, CA", "South El Monte, CA"),
        ("Orange, CA", "Orange, CA", "Orange County, CA"),
        ("Walnut, CA", "Walnut, CA", "Walnut Creek, CA"),
        ("Arcadia, CA", "Arcadia, CA", "Arcadia, FL"),
        ("Industry, CA", "City of Industry, CA", "Industry, PA"),
    ],
)
def test_single_city_pick_matches_only_that_city(picked, inside, look_alike) -> None:
    area = place_areas.area_for(picked)
    assert area is not None
    assert location_in_area(inside, area)
    assert not location_in_area(look_alike, area)


# --------------------------------------------------------------------------- #
# Board filter (SQL) agrees with the Python predicate
# --------------------------------------------------------------------------- #

_COUNTER = itertools.count()


def _session_with(locations: list[str]) -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    for loc in locations:
        n = next(_COUNTER)
        s.add(ApplicationRecord(
            job_title=loc, company="Acme", job_url=f"https://x.example/{n}", location=loc,
            is_remote=False, remote_scope="", state_codes="",
        ))
    s.flush()
    return s


def _board(s: Session, typed: str) -> set[str]:
    cond = place_filter(ApplicationRecord, typed, location_strict=True)
    return {r.job_title for r in s.query(ApplicationRecord).filter(cond).all()}


BOARD_ROWS = (
    [f"{c}, CA" for c in SGV_CITIES + NOC_CITIES]
    + ["Orange, NJ", "Orange County, CA", "Walnut Creek, CA", "Cypress, TX", "Pasadena, TX",
       "Industry, PA", "Arcadia, FL", "Irvine, CA", "Los Angeles, CA", "Beverly Hills, CA"]
)


@pytest.mark.parametrize("typed", [SGV, "626", "SGV"])
def test_board_sgv_expands_to_its_cities(typed: str) -> None:
    s = _session_with(BOARD_ROWS)
    assert _board(s, typed) == {f"{c}, CA" for c in SGV_CITIES}


@pytest.mark.parametrize("typed", [NOC, "North OC", "Fullerton area"])
def test_board_north_oc_expands_to_its_cities(typed: str) -> None:
    s = _session_with(BOARD_ROWS)
    assert _board(s, typed) == {f"{c}, CA" for c in NOC_CITIES}


def test_board_sql_and_python_predicates_agree() -> None:
    rows = BOARD_ROWS + [
        "Orange County Choppers, Newburgh, NY", "La Habra Heights, CA", "South Pasadena, CA",
        "Anaheim, Orange County, CA", "La Brea, Los Angeles, CA",
    ]
    s = _session_with(rows)
    for typed in (SGV, NOC, "Arcadia, CA", "Covina, CA", "Orange, CA", "Los Angeles", "Koreatown"):
        area = place_areas.area_for(typed)
        assert _board(s, typed) == {r for r in rows if location_in_area(r, area)}, typed


def test_board_single_city_arcadia() -> None:
    s = _session_with(BOARD_ROWS + ["Arcadia, California"])
    assert _board(s, "Arcadia, CA") == {"Arcadia, CA", "Arcadia, California"}


def test_board_la_metro_still_expands() -> None:
    s = _session_with(BOARD_ROWS)
    got = _board(s, "Los Angeles, CA")
    assert {"Los Angeles, CA", "Beverly Hills, CA", "Pasadena, CA", "El Monte, CA"} <= got
    assert "Irvine, CA" not in got


# --------------------------------------------------------------------------- #
# Find Work: post-search location gate
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(("saved", "inside", "outside"), [
    (SGV, "Arcadia, CA", "Irvine, CA"),
    (SGV, "West Covina, CA, US", "Walnut Creek, CA"),
    (NOC, "Fullerton, CA", "Orange, NJ"),
    (NOC, "Brea, CA", "Cypress, TX"),
])
def test_pipeline_location_gate_accepts_area_cities(saved, inside, outside) -> None:
    for prefs in (
        {"preferred_locations": [saved]},
        {"preferred_places": [{"label": saved, "match_scope": "region", "country_code": "US"}]},
    ):
        assert location_matches_preferences(inside, False, include_remote=False, **prefs)
        assert not location_matches_preferences(outside, False, include_remote=False, **prefs)


# --------------------------------------------------------------------------- #
# Find Work: JobSpy fan-out and the per-place budget
# --------------------------------------------------------------------------- #

def test_area_searches_anchor_cities_never_the_literal_label() -> None:
    assert search_places(SGV) == [("El Monte, CA", 10), ("Pasadena, CA", 10), ("West Covina, CA", 10)]
    assert search_places("626") == search_places(SGV)
    assert search_places(NOC) == [("Fullerton, CA", 10), ("Anaheim, CA", 10)]
    assert search_places("Arcadia, CA") == [("Arcadia, CA", None)]
    assert search_places("Los Angeles, CA") == [("Los Angeles, CA", None)]


def test_area_tasks_cover_every_role_at_every_anchor_and_map_back() -> None:
    tasks, origin = _place_major_search_tasks([SGV, "Remote"], ["it support", "data analyst"])
    assert tasks == [
        ("it support", "El Monte, CA"), ("it support", "Pasadena, CA"), ("it support", "West Covina, CA"),
        ("data analyst", "El Monte, CA"), ("data analyst", "Pasadena, CA"), ("data analyst", "West Covina, CA"),
        ("it support", "Remote"), ("data analyst", "Remote"),
    ]
    assert origin["pasadena, ca"] == (SGV, 10)
    assert origin["remote"] == ("Remote", None)


def test_area_queries_count_toward_the_task_cap() -> None:
    """Six SGV role queries are real queries: the cap sees all of them and
    keyword queries make room, so the area never runs past the cap unseen."""
    tasks, _ = _place_major_search_tasks([SGV], ["it support", "help desk", "sql"])
    kept = _cap_search_tasks(tasks, cap=6, role_terms={"it support", "help desk"})
    assert len(tasks) == 9
    assert len(kept) == 6
    assert all(term != "sql" for term, _loc in kept)


def test_budget_area_anchors_share_one_place_and_minimum_scales() -> None:
    budget = _BoardPlaceBudget(max_unique=2, minimum_queries=1, anchors_per_place={SGV: 3})
    rows = [{"url": "a"}, {"url": "b"}]
    assert budget.record("indeed", SGV, rows) is False
    assert budget.record("indeed", SGV, rows) is False
    assert budget.record("indeed", SGV, []) is True
    assert budget.record("indeed", "Remote", rows) is True


def _install_fakes(monkeypatch, calls: list[dict], url_per_location: bool = False) -> None:
    def fake_search_jobs(*, search_term, location, is_remote, telemetry, distance=None, **_kw):
        calls.append({"term": search_term, "location": location, "distance": distance, "remote": bool(is_remote)})
        jobs = [
            {
                "title": search_term.title(),
                "company": f"Co {i}",
                "location": "Remote" if is_remote else location,
                "url": f"https://indeed.example/{search_term}/{is_remote}/{i}"
                + (f"/{location}" if url_per_location else ""),
                "source": "indeed",
                "description": "IT support for a local office.",
                "is_remote": bool(is_remote),
            }
            for i in range(60)
        ]
        telemetry.update({"finish_reason": "ok", "rows_found": len(jobs), "duration_s": 0.01, "error_sample": ""})
        return jobs

    import job_finder.models.database as database_module
    import job_finder.pipeline as pipeline_module
    import job_finder.tools.scrapers as scrapers_module

    monkeypatch.setattr(pipeline_module, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(database_module, "record_scrape_runs", lambda _rows: None)
    monkeypatch.setattr(scrapers_module, "get_registry", lambda: {})
    monkeypatch.setattr(scrapers_module, "run_scrapers", lambda **_kwargs: [])


def _config(max_unique: int, min_queries: int | None = None) -> dict:
    settings = {
        "ai_expand_roles": False,
        "max_parallel_searches": 1,
        "max_search_tasks": 12,
        "max_unique_jobs": max_unique,
        "max_days_old": 30,
    }
    if min_queries is not None:
        settings["min_queries_per_source"] = min_queries
    return {
        "job_boards": ["indeed"],
        "additional_sources": [],
        "search_settings": settings,
        "location_preferences": {"include_remote": True},
    }


def test_find_work_area_runs_anchors_at_area_radius(monkeypatch) -> None:
    calls: list[dict] = []
    _install_fakes(monkeypatch, calls)
    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = _config(max_unique=500)

    pipeline.search_all_jobs(roles=["IT Support", "Data Analyst"], locations=[SGV, "Remote"])

    onsite = [c for c in calls if not c["remote"]]
    assert {c["location"] for c in onsite} == {"El Monte, CA", "Pasadena, CA", "West Covina, CA"}
    assert all(c["distance"] == 10 for c in onsite)
    assert len(onsite) == 6
    assert {c["term"] for c in calls if c["remote"]} == {"it support", "data analyst"}
    assert not any("valley" in c["location"].lower() for c in calls)


def test_area_cap_spans_all_anchors_and_spares_other_places(monkeypatch) -> None:
    """60 new rows per query, cap 100, one query minimum per place. A plain
    place would stop after query 2; the area must first ask each anchor once
    (3 queries), then stop, and Remote still gets its own budget."""
    calls: list[dict] = []
    _install_fakes(monkeypatch, calls, url_per_location=True)
    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = _config(max_unique=100, min_queries=1)

    pipeline.search_all_jobs(roles=["IT Support", "Data Analyst"], locations=[SGV, "Remote"])

    onsite = [c["location"] for c in calls if not c["remote"]]
    assert sorted(onsite) == ["El Monte, CA", "Pasadena, CA", "West Covina, CA"]
    assert len([c for c in calls if c["remote"]]) >= 1


def test_find_work_area_results_survive_the_location_gate_once(monkeypatch) -> None:
    calls: list[dict] = []
    _install_fakes(monkeypatch, calls)
    pipeline = JobFinderPipeline(llm=None)
    pipeline.config = _config(max_unique=500)

    jobs = pipeline.search_all_jobs(roles=["IT Support"], locations=[NOC])

    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls))
    assert jobs, "North OC anchor rows must pass the post-search location gate"
    assert {j["location"] for j in jobs} <= {"Fullerton, CA", "Anaheim, CA"}


# --------------------------------------------------------------------------- #
# Side Quests: part-time source
# --------------------------------------------------------------------------- #

def test_parttime_area_runs_each_term_at_each_anchor_and_dedupes() -> None:
    from job_finder.tools.scrapers import indeed_parttime as mod

    calls: list[dict] = []

    def fake_search_jobs(**kw):
        calls.append(kw)
        return [{
            "title": f"{kw['search_term'].title()} Part-Time",
            "company": "Boba Spot",
            "location": "Arcadia, CA",
            "url": f"https://www.indeed.com/viewjob?jk={kw['search_term']}",
            "job_type": "parttime",
        }]

    with patch("job_finder.tools.job_search_tool.search_jobs", fake_search_jobs):
        rows = mod.search_indeed_parttime(place=SGV, max_days_old=3650)

    anchors = {"El Monte, CA", "Pasadena, CA", "West Covina, CA"}
    assert {c["location"] for c in calls} == anchors
    assert len(calls) == len(mod.SEARCH_TERMS) * 3
    assert all(c["distance"] == 10 for c in calls)
    assert len(rows) == len(mod.SEARCH_TERMS)


# --------------------------------------------------------------------------- #
# The frontend lists stay in sync with this module
# --------------------------------------------------------------------------- #

def test_frontend_place_lists_match_the_areas() -> None:
    places = (ROOT / "frontend/src/features/board/places.ts").read_text()
    catalog = (ROOT / "frontend/src/lib/location-catalog.ts").read_text()
    for area in place_areas.NAMED_AREAS:
        assert f"'{area.label}'" in places, area.label
        assert f"'{area.label}'" in catalog, area.label
        for alias in area.aliases:
            assert re.search(rf"'{re.escape(alias)}'", places, re.IGNORECASE), alias
    for city in SGV_CITIES + NOC_CITIES:
        assert f"'{city}'" in places, city


def test_backend_suggestions_offer_areas_without_a_state() -> None:
    from app.services.location_service import _search_local

    for typed, label in (("626", SGV), ("sgv", SGV), ("north oc", NOC), ("fullerton area", NOC)):
        hits = {s.label: s for s in _search_local(typed, 8)}
        assert label in hits, typed
        assert hits[label].region == "" and hits[label].country_code == "US"
