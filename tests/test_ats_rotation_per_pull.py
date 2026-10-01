"""Catalog rotation advances per pull, and boards seen on the board join every pull.

Real case (Oct 1 2026): the cold slice of each verified ATS catalog was keyed
to the UTC calendar day. A user who pulls twice a week only ever saw the
slices of the days he pulled. Over 11 pull days since Sep 16 the simulated
coverage was 49% of 1,642 Greenhouse boards, 58% of 1,519 Ashby, 85% of 544
Lever and 43% of 2,052 Workable. Boards in the skipped slices were never
scanned. Stripe's Greenhouse board (714 live jobs, a US-remote Engineering
Manager, Data Transformation) was in no list at all, and Airbnb's board was
in the verified list but not in the every-pull set even though Airbnb rows
reach the board through LinkedIn and BuiltIn every week.
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

HOST = "greenhouse"
T0 = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def _write_catalog(data_dir: Path, slugs: list[str], host: str = HOST) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"{host}_verified_full.txt").write_text(
        "\n".join(slugs) + "\n", encoding="utf-8"
    )


@pytest.fixture
def ats_discovery(monkeypatch, tmp_path):
    mod = importlib.import_module("job_finder.tools.scrapers._ats_discovery")
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.delenv("QUESTBOARD_DISABLE_ATS_CATALOG_ROTATION", raising=False)
    return mod


# ---------------------------------------------------------------------------
# A. rotation advances per pull
# ---------------------------------------------------------------------------


def test_three_pulls_on_any_calendar_days_cover_the_whole_catalog(ats_discovery, tmp_path):
    slugs = [f"co-{i:03d}" for i in range(200)]
    _write_catalog(tmp_path, slugs)
    pull = partial(ats_discovery.verified_rotation_slugs, HOST, batch_size=80)

    first = pull(at=T0)
    assert first == set(slugs[0:80])
    # a second call inside the same run (or a retry minutes later) repeats the slice
    assert pull(at=T0 + timedelta(minutes=1)) == first
    assert pull(at=T0 + timedelta(days=3)) == set(slugs[80:160])
    assert pull(at=T0 + timedelta(days=9)) == set(slugs[160:200] + slugs[0:40])


def test_cursor_survives_in_the_cache_dir_next_to_the_discovery_cache(ats_discovery, tmp_path):
    _write_catalog(tmp_path, [f"co-{i:03d}" for i in range(200)])
    ats_discovery.verified_rotation_slugs(HOST, batch_size=80, at=T0)
    assert (tmp_path / "cache" / f"ats_rotation_{HOST}.json").exists()
    assert not (tmp_path / "cache" / f"ats_discovered_{HOST}.json").exists()


@pytest.mark.parametrize(
    "garbage",
    ["{not json", "[1, 2, 3]", '{"cursor": "eighty", "advanced_at": "yesterday"}'],
)
def test_corrupt_cursor_file_starts_over_at_zero(ats_discovery, tmp_path, garbage):
    slugs = [f"co-{i:03d}" for i in range(200)]
    _write_catalog(tmp_path, slugs)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"ats_rotation_{HOST}.json").write_text(garbage, encoding="utf-8")

    first = ats_discovery.verified_rotation_slugs(HOST, batch_size=80, at=T0)
    assert first == set(slugs[0:80])
    nxt = ats_discovery.verified_rotation_slugs(HOST, batch_size=80, at=T0 + timedelta(days=1))
    assert nxt == set(slugs[80:160])


def test_env_switch_still_disables_rotation(ats_discovery, tmp_path, monkeypatch):
    _write_catalog(tmp_path, [f"co-{i:03d}" for i in range(200)])
    monkeypatch.setenv("QUESTBOARD_DISABLE_ATS_CATALOG_ROTATION", "1")
    assert ats_discovery.verified_rotation_slugs(HOST, batch_size=80, at=T0) == set()


# ---------------------------------------------------------------------------
# B. companies already on the board join the every-pull set
# ---------------------------------------------------------------------------


def test_verified_list_resolves_names_the_catalog_does_not_know(tmp_path):
    from job_finder.config.company_catalog import resolve_watchlist

    _write_catalog(tmp_path, ["airbnb", "stripe"])
    out = resolve_watchlist(["Airbnb", "Stripe", "Nobody Inc"], data_dir=tmp_path)
    assert out == [
        {"name": "Airbnb", "ats": "greenhouse", "slug": "airbnb"},
        {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"},
        {"name": "Nobody Inc", "ats": "unknown", "slug": ""},
    ]


def test_exact_verified_match_beats_a_catalog_substring_guess(tmp_path):
    """"Scale" used to resolve to PlanetScale through the catalog's partial match."""
    from job_finder.config.company_catalog import resolve_watchlist

    _write_catalog(tmp_path, ["scale"], host="lever")
    out = resolve_watchlist(["Scale"], data_dir=tmp_path)
    assert out == [{"name": "Scale", "ats": "lever", "slug": "scale"}]


def test_shipped_greenhouse_catalog_knows_airbnb_and_stripe():
    from job_finder.config.company_catalog import resolve_watchlist

    out = {e["name"]: (e["ats"], e["slug"]) for e in resolve_watchlist(["Airbnb", "Stripe"])}
    assert out == {"Airbnb": ("greenhouse", "airbnb"), "Stripe": ("greenhouse", "stripe")}


def test_auto_boards_are_capped_per_host_by_row_count_not_by_name(tmp_path):
    """A name cap kept 99 of 368 resolvable boards: the top names by row count
    come from LinkedIn and Indeed and resolve to nothing."""
    from job_finder.board_companies import watchlist_with_board_companies
    from job_finder.config.company_catalog import resolve_watchlist

    _write_catalog(tmp_path, [f"co-{i:03d}" for i in range(200)])
    _write_catalog(tmp_path, [f"lv-{i:03d}" for i in range(11)], host="lever")
    # row-count order: 300 unresolvable aggregator names first, then the boards
    names = [f"Aggregator Only {i}" for i in range(300)]
    names += [f"Co {i:03d}" for i in range(200)] + [f"Lv {i:03d}" for i in range(11)]
    raw = [{"name": "User Co", "ats": "greenhouse", "slug": "co-150"}, "Typed Name"]

    out = watchlist_with_board_companies(
        raw, fetch=lambda **_: names, resolve=partial(resolve_watchlist, data_dir=tmp_path),
    )
    assert out[:2] == raw
    auto = out[2:]
    assert all(isinstance(e, dict) and e["ats"] != "unknown" for e in auto)
    greenhouse = [e["slug"] for e in auto if e["ats"] == "greenhouse"]
    lever = [e["slug"] for e in auto if e["ats"] == "lever"]
    assert len(greenhouse) == 120
    assert greenhouse[:3] == ["co-000", "co-001", "co-002"]
    assert "co-150" not in greenhouse, "the user's own board never burns an auto slot"
    assert lever == [f"lv-{i:03d}" for i in range(11)]


def test_companies_seen_on_the_board_reach_the_ats_watchlist(tmp_path):
    from job_finder.board_companies import watchlist_with_board_companies
    from job_finder.config.company_catalog import resolve_watchlist
    from job_finder.pipeline import watchlist_tokens_by_ats

    _write_catalog(tmp_path, ["airbnb", "billcom", "stripe"])
    raw = [{"name": "BILL", "ats": "greenhouse", "slug": "billcom"}]
    merged = watchlist_with_board_companies(
        raw,
        fetch=lambda **_: ["Airbnb", "BILL", "Stripe", "", "Airbnb", "Nobody Inc"],
        resolve=partial(resolve_watchlist, data_dir=tmp_path),
    )
    assert merged == [
        raw[0],
        {"name": "Airbnb", "ats": "greenhouse", "slug": "airbnb"},
        {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"},
    ]

    by_ats = watchlist_tokens_by_ats(
        merged, resolve=partial(resolve_watchlist, data_dir=tmp_path),
    )
    assert by_ats == {"greenhouse": ["billcom", "airbnb", "stripe"]}


def test_fetch_asks_for_all_companies_on_the_board():
    from job_finder.board_companies import BOARD_NAME_FETCH, watchlist_with_board_companies

    seen: dict = {}

    def fetch(**kwargs):
        seen.update(kwargs)
        return []

    watchlist_with_board_companies([], workspace_id="ws-1", fetch=fetch)
    assert seen == {"workspace_id": "ws-1", "cap": BOARD_NAME_FETCH}
    assert BOARD_NAME_FETCH >= 1500


def test_a_database_error_never_blocks_the_pull():
    from job_finder.board_companies import watchlist_with_board_companies

    def boom(**_):
        raise RuntimeError("database is locked")

    assert watchlist_with_board_companies(["Anthropic"], fetch=boom) == ["Anthropic"]


@pytest.fixture
def db(tmp_path):
    from job_finder.models import database

    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def test_companies_on_board_query_keeps_recent_found_career_rows(db):
    from job_finder.board_companies import companies_on_board

    for i in range(3):
        db.save_application(job_title="EM", company="Airbnb", job_url=f"https://a/{i}")
    db.save_application(job_title="EM", company="Stripe", job_url="https://s/1")
    db.save_application(job_title="EM", company="", job_url="https://blank/1")
    old = db.save_application(job_title="EM", company="Old Co", job_url="https://o/1")
    gone = db.save_application(job_title="EM", company="Expired Co", job_url="https://e/1")
    db.update_application_status(gone.id, "expired")
    db.save_application(
        job_title="Focus group", company="Fieldwork", job_url="https://f/1", vertical="study",
    )
    session = db.get_session()
    try:
        row = session.query(db.ApplicationRecord).filter_by(id=old.id).one()
        row.date_found = datetime.now(timezone.utc) - timedelta(days=60)
        session.commit()
    finally:
        db._close_session()

    assert companies_on_board(days=45, cap=200) == ["Airbnb", "Stripe"]
    assert companies_on_board(days=45, cap=1) == ["Airbnb"]
