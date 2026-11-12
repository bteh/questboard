"""A company already on the board must get its own ATS board scanned even when
the shipped catalog can't name it.

Nov 12 2026: Trella Health was on the board through LinkedIn ("Manager, Data
Engineering", row 30103) while its Greenhouse board (slug ``trellahealth``)
listed "Data Engineering Manager", remote US, posted Nov 10. resolve_watchlist
returned ats="unknown" for "Trella Health" (the slug is in no seed, verified
list, or catalog), so the board lane dropped the name and no pull ever fetched
boards-api.greenhouse.io/v1/boards/trellahealth. The pipeline filters were not
the problem: replaying the real pull with that board in the watchlist saved
the row.
"""

from __future__ import annotations

import os

import pytest

from job_finder.board_companies import watchlist_with_board_companies


def _unresolved(names: list[str]) -> list[dict[str, str]]:
    return [{"name": n, "ats": "unknown", "slug": ""} for n in names]


def test_trella_health_on_board_via_linkedin_gets_its_greenhouse_board(monkeypatch):
    import job_finder.tools.scrapers._board_probe as board_probe

    asked: list[tuple[str, str]] = []

    def fake_probe_status(host: str):
        def probe(slug: str) -> int | None:
            asked.append((host, slug))
            return 200 if (host, slug) == ("greenhouse", "trellahealth") else 404

        return probe

    monkeypatch.setattr(board_probe, "probe_status", fake_probe_status)

    merged = watchlist_with_board_companies(
        [],
        fetch=lambda **_: ["Trella Health"],
        resolve=_unresolved,
    )

    assert {"name": "Trella Health", "ats": "greenhouse", "slug": "trellahealth"} in merged, (
        f"unresolved board company never reached an ATS board; probes asked: {asked}"
    )


def _counting_probe(answer):
    asked: list[tuple[str, str]] = []

    def probe_for(host: str):
        def probe(slug: str) -> int | None:
            asked.append((host, slug))
            return answer(host, slug)

        return probe

    return probe_for, asked


def test_a_cached_miss_is_not_probed_again_next_pull():
    from job_finder.board_name_probe import boards_for_unresolved

    probe_for, asked = _counting_probe(lambda host, slug: 404)
    entries = _unresolved(["Nobody Inc"])
    assert boards_for_unresolved(entries, probe_for=probe_for) == entries
    assert len(asked) == 4, "one probe per ATS host on the first pull"

    assert boards_for_unresolved(entries, probe_for=probe_for) == entries
    assert len(asked) == 4, "a remembered miss must not re-probe every pull"


def test_a_found_board_is_remembered_and_promoted_without_reprobing():
    from job_finder.board_name_probe import boards_for_unresolved

    probe_for, asked = _counting_probe(
        lambda host, slug: 200 if (host, slug) == ("greenhouse", "trellahealth") else 404
    )
    promoted: list[tuple[str, set[str]]] = []
    promote = lambda host, slugs: promoted.append((host, set(slugs))) or len(slugs)  # noqa: E731
    want = [{"name": "Trella Health", "ats": "greenhouse", "slug": "trellahealth"}]

    assert boards_for_unresolved(_unresolved(["Trella Health"]), probe_for=probe_for, promote=promote) == want
    assert promoted == [("greenhouse", {"trellahealth"})]
    first = len(asked)
    assert boards_for_unresolved(_unresolved(["Trella Health"]), probe_for=probe_for, promote=promote) == want
    assert len(asked) == first


def test_an_unreachable_host_is_not_remembered_as_a_miss():
    from job_finder.board_name_probe import boards_for_unresolved

    probe_for, asked = _counting_probe(lambda host, slug: None if host == "lever" else 404)
    boards_for_unresolved(_unresolved(["Flaky Co"]), probe_for=probe_for)
    boards_for_unresolved(_unresolved(["Flaky Co"]), probe_for=probe_for)
    assert len(asked) == 8


def test_new_probes_per_pull_are_bounded():
    from job_finder import board_name_probe

    probe_for, asked = _counting_probe(lambda host, slug: 404)
    names = [f"Aggregator Only {i}" for i in range(300)]
    board_name_probe.boards_for_unresolved(_unresolved(names), probe_for=probe_for)
    hosts = len(board_name_probe._VERIFIED_HOSTS)
    cap = board_name_probe.MAX_NEW_NAMES_PER_PULL
    assert len(asked) == cap * hosts
    assert {slug for _, slug in asked} == {f"aggregatoronly{i}" for i in range(cap)}, (
        "row-count order: the names the board shows most are probed first"
    )

    board_name_probe.boards_for_unresolved(_unresolved(names), probe_for=probe_for)
    assert len(asked) == 2 * cap * hosts
    assert {slug for _, slug in asked[cap * hosts:]} == {
        f"aggregatoronly{i}" for i in range(cap, 2 * cap)
    }, "the next pull moves down the list instead of re-asking"


def test_a_slow_host_cannot_stall_the_pull(monkeypatch):
    import threading
    import time

    from job_finder import board_name_probe

    monkeypatch.setattr(board_name_probe, "PROBE_DEADLINE_SECONDS", 0.2)
    release = threading.Event()

    def probe_for(host: str):
        def probe(slug: str) -> int | None:
            if host == "ashby":
                release.wait(5)
            return 404

        return probe

    started = time.monotonic()
    out = board_name_probe.boards_for_unresolved(_unresolved(["Slow Co"]), probe_for=probe_for)
    elapsed = time.monotonic() - started
    release.set()
    assert out == _unresolved(["Slow Co"])
    assert elapsed < 1.0
    assert board_name_probe.load_memo() == {}, "an unanswered host is asked again next pull"



@pytest.fixture
def db(tmp_path):
    from job_finder.models import database

    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


def test_a_company_seen_today_is_probed_before_stale_names_with_more_rows(db, monkeypatch):
    """Trella Health was #875 of 968 unresolved board names by row count
    (Nov 12 2026), ~73 pulls from its probe. Its one LinkedIn row was seen
    that day; names last seen 20+ days ago with more rows must wait."""
    from datetime import datetime, timedelta, timezone

    import job_finder.tools.scrapers._board_probe as board_probe
    from job_finder import board_name_probe

    stale = datetime.now(timezone.utc) - timedelta(days=21)
    for i in range(300):
        for j in range(3):
            db.save_application(
                job_title="Data Engineer", company=f"Aggregator Only {i}",
                job_url=f"https://agg/{i}/{j}",
            )
    session = db.get_session()
    try:
        session.query(db.ApplicationRecord).update(
            {"last_seen_at": stale, "date_found": stale}, synchronize_session=False,
        )
        session.commit()
    finally:
        db._close_session()
    trella = db.save_application(
        job_title="Manager, Data Engineering", company="Trella Health",
        job_url="https://www.linkedin.com/jobs/view/30103",
    )
    session = db.get_session()
    try:
        session.query(db.ApplicationRecord).filter_by(id=trella.id).update(
            {"last_seen_at": datetime.now(timezone.utc)}, synchronize_session=False,
        )
        session.commit()
    finally:
        db._close_session()

    probe_for, asked = _counting_probe(
        lambda host, slug: 200 if (host, slug) == ("greenhouse", "trellahealth") else 404
    )
    monkeypatch.setattr(board_probe, "probe_status", probe_for)

    merged = watchlist_with_board_companies([], resolve=_unresolved)

    assert {"name": "Trella Health", "ats": "greenhouse", "slug": "trellahealth"} in merged
    probed = list(dict.fromkeys(slug for _, slug in asked))
    assert probed[0] == "trellahealth"
    assert len(probed) == board_name_probe.MAX_NEW_NAMES_PER_PULL
