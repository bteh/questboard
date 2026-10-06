"""A closed-job page that answers HTTP 200 must still take the row off the board.

Real case (Brian, Oct 6 2026): postings on his board opened to "sorry, not
found" pages. The link checker marks a row dead only on 404/410, so hosts that
keep the URL alive and render a closed notice were stamped alive, and since
0.2.13 that stamp (freshness basis "verified_open") kept them on the board
past the freshness window. Live probe of 99 board links: 6 of 8 BuiltIn rows
stamped alive were dead, 4 of 8 LinkedIn, 4 Workable; 153 of 471 rows were on
the board only because of the stamp.

Rules under test:
- a closed-page template counts only on its own host, so a generic phrase on
  an unrelated page never kills a row;
- check_urls reads the body for template hosts and marks the row dead when
  the template matches, while 403/429/999 and transport errors stay unknown;
- a versioned repair resets alive rows on template hosts to unknown with no
  last_checked_at, so the next re-verify ticks re-check them first.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from threading import Lock as ThreadLock
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from job_finder.closed_pages import closed_page, template_for  # noqa: E402
from job_finder.host_pacing import HostPacer  # noqa: E402
from job_finder.models.link_status_repair import (  # noqa: E402
    LINK_STATUS_REPAIR_NAME,
    LINK_STATUS_REPAIR_VERSION,
    repair_link_status,
)

# Phrasing copied from the live pages on Oct 6 2026.
BUILTIN_SIFT = "https://builtin.com/job/software-engineering-manager-data/9063200"
BUILTIN_SIFT_BODY = (
    '<h1>Software Engineering Manager (Data)</h1><div class="mb-sm">'
    '<span class="font-barlow text-lava fs-md fw-regular">Sorry, this job was '
    "removed at 11:38 p.m. (UTC) on Thursday, Aug 20, 2026</span></div>"
)
BUILTIN_LIVE = "https://builtin.com/job/staff-data-engineer-core-migrations/10017738"
BUILTIN_LIVE_BODY = (
    "<title>Staff Data Engineer, Core Migrations - Machinify | Built In</title>"
    '<a class="btn">Apply Now</a>'
)
LINKEDIN_WHATNOT = "https://www.linkedin.com/jobs/view/4459427317"
LINKEDIN_WHATNOT_FINAL = (
    "https://www.linkedin.com/jobs/senior-data-engineer-jobs?trk=expired_jd_redirect"
)
LINKEDIN_BANNER = "https://www.linkedin.com/jobs/view/4459205755"
LINKEDIN_BANNER_BODY = (
    '<figure><span class="closed-job__icon"></span>'
    '<figcaption class="closed-job__flavor--closed">No longer accepting '
    "applications</figcaption></figure>"
)
LINKEDIN_CALANCE = "https://www.linkedin.com/jobs/view/4446417189"
LINKEDIN_CALANCE_BODY = (
    '<code id="i18n_redirected_from_missing_job" style="display: none">'
    '<!--"This job is no longer available, but here are similar jobs you might '
    'like."--></code>'
)
LINKEDIN_LIVE = "https://www.linkedin.com/jobs/view/4466579484"
LINKEDIN_LIVE_BODY = (
    "<title>Staff Data Engineer, Analytics at Whatnot | LinkedIn Jobs</title>"
    '<button class="apply-button">Apply</button>'
)
WORKABLE_AUTORENTALS = "https://apply.workable.com/autorentals/j/3844870A3A"
WORKABLE_TIGER = "https://apply.workable.com/j/9E3A3A69EA"
GETRO_TECHSTARS = (
    "https://jobs.techstars.com/companies/gorgias-com/jobs/"
    "96022508-ai-deployment-manager-enterprise"
)
GREENHOUSE_REDDIT = "https://job-boards.greenhouse.io/reddit/jobs/8072046"
GREENHOUSE_OLD_BOARD = "https://boards.greenhouse.io/coinbase/jobs/8008047"
LEVER_ANCHORAGE = "https://jobs.lever.co/anchorage/f509f586-c45d-4c66-8ad1-a09527ab3b03"
# A Phenom careers site reached through the getro_startups scraper. Its page
# source carries "no longer available" as a hidden i18n string on every page,
# live or not; the live probe misread it as closed.
PHENOM_SVB = "https://jobs.firstcitizens.com/jobs/34605?lang=en-us"
PHENOM_SVB_BODY = (
    '{"ERROR":{"NO_JOBS_404":"We\'re sorry, but it looks like this job may be '
    'no longer available or does not exist."}}'
    '{"@type":"JobPosting","title":"Lead Data Engineer - Data Platform"}'
)


# ── templates, one per real posting ─────────────────────────────────────────


def test_builtin_sift_stack_removed_page_is_closed() -> None:
    assert closed_page(BUILTIN_SIFT, BUILTIN_SIFT, 200, BUILTIN_SIFT_BODY)


def test_builtin_no_longer_wording_is_closed() -> None:
    body = "<span>Sorry, this job is no longer available on Built In.</span>"
    assert closed_page(BUILTIN_SIFT, BUILTIN_SIFT, 200, body)


def test_linkedin_whatnot_expired_redirect_is_closed() -> None:
    assert closed_page(LINKEDIN_WHATNOT, LINKEDIN_WHATNOT_FINAL, 200, "<html>jobs</html>")


def test_linkedin_no_longer_accepting_banner_is_closed() -> None:
    assert closed_page(LINKEDIN_BANNER, LINKEDIN_BANNER, 200, LINKEDIN_BANNER_BODY)


def test_linkedin_calance_no_longer_available_is_closed() -> None:
    assert closed_page(LINKEDIN_CALANCE, LINKEDIN_CALANCE, 200, LINKEDIN_CALANCE_BODY)


def test_workable_autorentals_oops_redirect_is_closed() -> None:
    assert closed_page(
        WORKABLE_AUTORENTALS, "https://apply.workable.com/oops", 200, "<title>Workable</title>"
    )


def test_workable_tiger_analytics_not_found_redirect_is_closed() -> None:
    assert closed_page(
        WORKABLE_TIGER,
        "https://apply.workable.com/tiger-analytics/?not_found=true",
        200,
        "<title>Tiger Analytics Inc. - Current Openings</title>",
    )


def test_getro_board_no_longer_available_is_closed() -> None:
    body = "<h1>This job is no longer available</h1>"
    assert closed_page(GETRO_TECHSTARS, GETRO_TECHSTARS, 200, body)


def test_greenhouse_reddit_no_longer_open_is_closed() -> None:
    body = "<p>The job you are looking for is no longer open.</p>"
    assert closed_page(GREENHOUSE_REDDIT, GREENHOUSE_REDDIT, 200, body)
    assert closed_page(GREENHOUSE_OLD_BOARD, GREENHOUSE_OLD_BOARD, 200, body)


def test_lever_anchorage_no_longer_accepting_is_closed() -> None:
    body = "<div>This job is no longer accepting applications.</div>"
    assert closed_page(LEVER_ANCHORAGE, LEVER_ANCHORAGE, 200, body)


# ── a template never fires off its own host ─────────────────────────────────


def test_a_live_builtin_page_stays_alive() -> None:
    assert not closed_page(BUILTIN_LIVE, BUILTIN_LIVE, 200, BUILTIN_LIVE_BODY)


def test_a_live_linkedin_page_stays_alive() -> None:
    assert not closed_page(LINKEDIN_LIVE, LINKEDIN_LIVE, 200, LINKEDIN_LIVE_BODY)


def test_a_live_greenhouse_page_stays_alive() -> None:
    body = "<h1>Principal Data Scientist, Ads</h1><button>Apply for this job</button>"
    assert not closed_page(GREENHOUSE_REDDIT, GREENHOUSE_REDDIT, 200, body)


def test_an_unlisted_host_saying_no_longer_available_stays_alive() -> None:
    assert not closed_page(PHENOM_SVB, PHENOM_SVB, 200, PHENOM_SVB_BODY)
    assert template_for(PHENOM_SVB) is None


def test_a_phrase_on_a_page_the_row_redirected_off_host_to_stays_alive() -> None:
    body = "<p>This job is no longer available</p>"
    assert not closed_page(BUILTIN_SIFT, "https://example.com/careers", 200, body)


def test_a_bot_wall_with_the_phrase_is_not_a_closed_page() -> None:
    assert not closed_page(BUILTIN_SIFT, BUILTIN_SIFT, 403, BUILTIN_SIFT_BODY)


# ── check_urls on a real board table ────────────────────────────────────────


class _Resp:
    def __init__(self, code: int, url: str = "") -> None:
        self.status_code = code
        self.url = url


class _PageResp(_Resp):
    def __init__(self, code: int, body: str, url: str = "") -> None:
        super().__init__(code, url)
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def iter_content(self, _chunk_size, decode_unicode=False):
        yield self.body


@pytest.fixture()
def board(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.application import ApplicationRecord
    from app.models.database import get_db, init_db
    from app.services import application_service

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    try:
        yield SimpleNamespace(db=db, svc=application_service, AR=ApplicationRecord)
    finally:
        generator.close()


def _add(board, title: str, url: str, source: str, status: str = "unknown"):
    row = board.AR(
        job_title=title, company="Acme", job_url=url, url_status=status, source=source
    )
    board.db.add(row)
    board.db.commit()
    return row


def _statuses(board) -> dict[str, str]:
    return {row.job_title: row.url_status for row in board.db.query(board.AR).all()}


def test_check_urls_marks_a_soft_closed_builtin_row_dead_before_the_apply_target(board) -> None:
    _add(board, "Sift Stack manager", BUILTIN_SIFT, "builtin")

    with (
        patch("requests.head", return_value=_Resp(200, BUILTIN_SIFT)),
        patch("requests.get", return_value=_PageResp(200, BUILTIN_SIFT_BODY, BUILTIN_SIFT)),
        patch("job_finder.tools.scrapers.builtin.fetch_builtin_detail") as detail,
    ):
        result = board.svc.check_urls(board.db)

    assert result == {"checked": 1, "alive": 0, "dead": 1, "unknown": 0}
    assert _statuses(board) == {"Sift Stack manager": "dead"}
    detail.assert_not_called()


def test_check_urls_marks_a_workable_oops_redirect_dead(board) -> None:
    _add(board, "AutoRentals lead", WORKABLE_AUTORENTALS, "workable")
    oops = "https://apply.workable.com/oops"

    with (
        patch("requests.head", return_value=_Resp(200, oops)),
        patch("requests.get", return_value=_PageResp(200, "<title>Workable</title>", oops)),
    ):
        result = board.svc.check_urls(board.db)

    assert result == {"checked": 1, "alive": 0, "dead": 1, "unknown": 0}
    assert _statuses(board) == {"AutoRentals lead": "dead"}


def test_check_urls_keeps_a_live_template_host_row_alive(board) -> None:
    _add(board, "Machinify staff", BUILTIN_LIVE, "builtin")

    with (
        patch("requests.head", return_value=_Resp(200, BUILTIN_LIVE)),
        patch("requests.get", return_value=_PageResp(200, BUILTIN_LIVE_BODY, BUILTIN_LIVE)),
        patch(
            "job_finder.tools.scrapers.builtin.fetch_builtin_detail",
            return_value={"direct_application_url": ""},
        ),
    ):
        result = board.svc.check_urls(board.db)

    assert result == {"checked": 1, "alive": 1, "dead": 0, "unknown": 0}


def test_check_urls_keeps_a_bot_wall_unknown(board) -> None:
    _add(board, "Blocked at BuiltIn", BUILTIN_SIFT, "builtin")
    _add(board, "Blocked at LinkedIn", LINKEDIN_WHATNOT, "linkedin")

    def fake_head(url, **_kwargs):
        return _Resp(403 if "builtin" in url else 999, url)

    with (
        patch("requests.head", side_effect=fake_head),
        patch("requests.get") as get,
        patch("job_finder.tools.scrapers.builtin.fetch_builtin_detail", return_value={}),
    ):
        result = board.svc.check_urls(board.db)

    assert result == {"checked": 2, "alive": 0, "dead": 0, "unknown": 2}
    assert set(_statuses(board).values()) == {"unknown"}
    get.assert_not_called()


# ── the repair resets stale alive stamps on template hosts ──────────────────

STAMP = "2026-09-23 04:19:02.061323"
UPDATED = "2026-09-20T00:00:00+00:00"


@pytest.fixture()
def engine(tmp_path):
    """Temp DB only; the desktop runtime's DB is a symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, job_url VARCHAR, url_status VARCHAR,"
            " last_checked_at DATETIME, updated_at VARCHAR)"
        ))
    return eng


def _seed(engine, job_url: str, url_status: str = "alive") -> int:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO applications (job_url, url_status, last_checked_at, updated_at)"
                " VALUES (:u, :s, :c, :t)"
            ),
            {"u": job_url, "s": url_status, "c": STAMP, "t": UPDATED},
        )
        return int(conn.execute(text("SELECT max(id) FROM applications")).scalar())


def _row(engine, row_id: int) -> tuple:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT url_status, last_checked_at, updated_at FROM applications"
                " WHERE id = :i"
            ),
            {"i": row_id},
        ).one()


def test_the_repair_resets_an_alive_builtin_row_and_leaves_ashby_alone(engine) -> None:
    builtin = _seed(engine, BUILTIN_SIFT)
    ashby = _seed(engine, "https://jobs.ashbyhq.com/horizon3ai/4651e6b3-a8b5-484f-ac87-5b6ca04581d1")
    dead_builtin = _seed(engine, "https://builtin.com/job/staff-data-engineer/9690637", "dead")

    assert repair_link_status(engine) == 1

    assert _row(engine, builtin) == ("unknown", None, UPDATED)
    assert _row(engine, ashby) == ("alive", STAMP, UPDATED)
    assert _row(engine, dead_builtin) == ("dead", STAMP, UPDATED)


def test_the_repair_records_its_marker_and_a_second_run_touches_nothing(engine) -> None:
    _seed(engine, LINKEDIN_WHATNOT)
    _seed(engine, WORKABLE_AUTORENTALS)

    assert repair_link_status(engine) == 2
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT version FROM data_repairs WHERE name = :n"),
            {"n": LINK_STATUS_REPAIR_NAME},
        ).scalar()
    assert LINK_STATUS_REPAIR_NAME == "soft_closed_links"
    assert version == LINK_STATUS_REPAIR_VERSION

    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET url_status = 'alive', last_checked_at = :c"), {"c": STAMP})
    assert repair_link_status(engine) == 0
    with engine.begin() as conn:
        stamps = conn.execute(text("SELECT url_status, last_checked_at FROM applications")).all()
    assert stamps == [("alive", STAMP), ("alive", STAMP)]


def test_a_database_without_the_table_does_not_crash(tmp_path) -> None:
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert repair_link_status(eng) == 0


# ── per-host pacing: one in flight per host, hosts in parallel ──────────────
#
# Oct 6 2026, first 200-row batch after the repair: 79 of 87 LinkedIn HEADs
# answered 429 within 25 seconds and every one of those rows went unknown.


def _host(url: str) -> str:
    return url.split("/")[2]


def test_two_same_host_requests_never_overlap_while_two_hosts_do() -> None:
    pacer = HostPacer(1.0, sleeper=lambda _s: None, clock=lambda: 0.0)
    guard = ThreadLock()
    in_flight: dict[str, int] = {}
    peak: dict[str, int] = {}
    order: list[tuple[str, str]] = []
    both_hosts_in_flight = Barrier(2, timeout=5)

    def fetch(url: str) -> None:
        host = _host(url)

        def request() -> None:
            with guard:
                in_flight[host] = in_flight.get(host, 0) + 1
                peak[host] = max(peak.get(host, 0), in_flight[host])
                order.append((host, "start"))
            if host != "www.linkedin.com":
                both_hosts_in_flight.wait()
            time.sleep(0.02)
            with guard:
                in_flight[host] -= 1
                order.append((host, "end"))

        pacer.run(url, request)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(fetch, [LINKEDIN_WHATNOT, LINKEDIN_BANNER, BUILTIN_SIFT, GREENHOUSE_REDDIT]))

    assert peak["www.linkedin.com"] == 1
    assert [step for host, step in order if host == "www.linkedin.com"] == [
        "start", "end", "start", "end",
    ]
    assert not both_hosts_in_flight.broken


def test_the_sleeper_runs_between_same_host_calls_and_never_between_hosts() -> None:
    sleeps: list[float] = []
    pacer = HostPacer(1.0, sleeper=sleeps.append, clock=lambda: 100.0)

    pacer.run(LINKEDIN_WHATNOT, lambda: "a")
    pacer.run(BUILTIN_SIFT, lambda: "b")
    assert sleeps == []
    pacer.run(LINKEDIN_BANNER, lambda: "c")
    assert sleeps == [1.0]
    pacer.run(GREENHOUSE_REDDIT, lambda: "d")
    assert sleeps == [1.0]


def test_a_host_idle_longer_than_the_spacing_is_not_slept() -> None:
    sleeps: list[float] = []
    now = [100.0]
    pacer = HostPacer(1.0, sleeper=sleeps.append, clock=lambda: now[0])

    pacer.run(LINKEDIN_WHATNOT, lambda: "a")
    now[0] += 1.5
    pacer.run(LINKEDIN_BANNER, lambda: "b")
    assert sleeps == []


def test_check_urls_paces_the_head_and_body_read_of_one_host(board) -> None:
    sleeps: list[float] = []
    _add(board, "AutoRentals lead", WORKABLE_AUTORENTALS, "workable")
    _add(board, "Plain host", "https://x.example/live", "test")

    with (
        patch("requests.head", side_effect=lambda url, **_k: _Resp(200, url)),
        patch(
            "requests.get",
            side_effect=lambda url, **_k: _PageResp(200, "<title>Workable</title>", url),
        ),
        patch(
            "job_finder.host_pacing.HostPacer",
            lambda *_a, **_k: HostPacer(1.0, sleeper=sleeps.append, clock=lambda: 0.0),
        ),
    ):
        result = board.svc.check_urls(board.db)

    assert result == {"checked": 2, "alive": 2, "dead": 0, "unknown": 0}
    assert sleeps == [1.0]
