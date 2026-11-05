"""A job URL that redirects to a generic listing page is a closed job.

Real cases (Brian's board, Nov 5 2026): the link checker treated a closed job
as dead only when Greenhouse redirected to another greenhouse.io page. Closed
jobs that redirect anywhere else land on a 200 index page, got stamped alive,
and the still-open freshness rule ("verified_open") kept them on the board for
months. Live probe of rows kept only by that stamp: 15 of 15 Himalayas rows
redirected to himalayas.app/jobs, 5 of 10 Greenhouse rows redirected to a
company careers index (3Cloud's posting answers 404 on the Greenhouse API).

A redirect that keeps the job's own id (Descript's gh_jid, Elastic's job page)
is a live job and must stay alive.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

# (requested job URL, where the live site redirected it on Nov 5 2026)
CLOSED = {
    "3Cloud": (
        "https://job-boards.greenhouse.io/3cloud/jobs/8682596002?gh_jid=8682596002",
        "https://3cloudsolutions.com/join-us/",
    ),
    "Databricks": (
        "https://databricks.com/company/careers/open-positions/job?gh_jid=8627551002",
        "https://www.databricks.com/company/careers/open-positions",
    ),
    "Instacart": (
        "https://instacart.careers/job/?gh_jid=8091191",
        "https://www.instacart.careers/current-openings",
    ),
    "FiscalNote": (
        "https://himalayas.app/companies/fiscalnote/jobs/director-data-analytics-business-intelligence",
        "https://himalayas.app/jobs",
    ),
}
LIVE = {
    "Descript": (
        "https://boards.greenhouse.io/descript/jobs/7780518003?gh_jid=7780518003",
        "https://job-boards.greenhouse.io/descript/jobs/7780518003?gh_jid=7780518003",
    ),
    "Elastic": (
        "https://jobs.elastic.co/jobs?gh_jid=8079636&gh_jid=8079636",
        "https://jobs.elastic.co/jobs/finance-it-operations/united-states/agentic-ai-engineer/8079636",
    ),
    "Bill": (
        "https://www.bill.com/job?6116018004&gh_jid=6116018004",
        "https://www.bill.com/job?6116018004&gh_jid=6116018004",
    ),
}


class _Resp:
    def __init__(self, code: int, url: str) -> None:
        self.status_code = code
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def iter_content(self, _chunk_size, decode_unicode=False):
        yield b"<title>Careers</title>"

    def json(self):
        raise ValueError("not json")


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


def _check(board, cases: dict[str, tuple[str, str]]) -> dict[str, str]:
    redirects = {}
    for company, (requested, final) in cases.items():
        source = "himalayas" if "himalayas" in requested else "greenhouse"
        board.db.add(
            board.AR(
                job_title=f"{company} role",
                company=company,
                job_url=requested,
                url_status="alive",
                source=source,
            )
        )
        redirects[requested] = final
    board.db.commit()

    def fake(url, **_kwargs):
        return _Resp(200, redirects.get(url, url))

    with patch("requests.head", side_effect=fake), patch("requests.get", side_effect=fake):
        board.svc.check_urls(board.db)
    return {row.company: row.url_status for row in board.db.query(board.AR).all()}


@pytest.mark.parametrize("company", sorted(CLOSED))
def test_a_job_redirected_to_a_listing_index_is_dead(board, company) -> None:
    assert _check(board, {company: CLOSED[company]}) == {company: "dead"}


@pytest.mark.parametrize("company", sorted(LIVE))
def test_a_redirect_that_keeps_the_job_id_stays_alive(board, company) -> None:
    assert _check(board, {company: LIVE[company]}) == {company: "alive"}
