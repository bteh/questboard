"""A full page of MCP search results must fit inside an agent's tool-result cap.

Real failure, 2026-07-24: a `find_and_rank` run scraped 126 fresh jobs, then
died without ranking any of them. `search_work` at its own `_MAX_RESULTS` page
returned 84,647 characters and the Claude CLI refused it four times in a row
("result (84,647 characters) exceeds maximum allowed tokens"), dumping the
payload to a file instead. The assistant burned the rest of the run shelling
out to `jq` and never reached `set_work_fit`, so the board kept showing the
previous day's verdicts.

The bulk was `description_excerpt`: 1,200 chars on every one of 50 rows, for a
list view that only needs enough text to judge whether a posting is worth a
closer look. `get_opportunity` still serves the long excerpt for finalists.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

# A posting body long enough that every row hits the excerpt ceiling.
_LONG_DESCRIPTION = (
    "We are hiring a data platform leader to own ingestion, warehousing, and "
    "analytics engineering across the company. You will manage a team, set "
    "technical direction for Snowflake and dbt, and partner with product. "
) * 40


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """A temp SQLite DB holding one full page of career rows.

    Never point this at the desktop runtime DB: it is a symlink to the repo's
    live board, so a test writing there would edit the user's real data.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.services.local_agent_service import _MAX_RESULTS
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)

    db.add_all([
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company=f"Company {i:03d}",
            location="Remote, United States",
            remote_scope="us",
            is_remote=True,
            work_type="remote",
            job_url=f"https://example.com/jobs/{i}",
            source="Greenhouse",
            description=_LONG_DESCRIPTION,
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now - timedelta(minutes=i),
            last_seen_at=now,
        )
        for i in range(_MAX_RESULTS + 10)
    ])
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_full_search_work_page_fits_an_agent_tool_result(seeded_db):
    from app.services.local_agent_service import (
        _MAX_RESULTS,
        _MCP_RESULT_CHAR_BUDGET,
        search_work,
    )

    result = search_work(
        seeded_db,
        queries=["Data Engineering Manager"],
        use_saved_preferences=False,
        page_size=_MAX_RESULTS,
    )

    assert result["result_count"] == _MAX_RESULTS, "the page should be full"
    size = len(json.dumps(result))
    assert size <= _MCP_RESULT_CHAR_BUDGET, (
        f"a full page serializes to {size:,} chars, over the "
        f"{_MCP_RESULT_CHAR_BUDGET:,} budget an agent tool result must fit"
    )


def test_full_side_quest_page_fits_an_agent_tool_result(tmp_path, monkeypatch):
    """The quest lane builds the same payload, so it carries the same risk."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.services.local_agent_service import (
        _MAX_RESULTS,
        _MCP_RESULT_CHAR_BUDGET,
        search_side_quests,
    )
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    db = next(get_db())
    now = datetime.now(timezone.utc)
    db.add_all([
        ApplicationRecord(
            job_title=f"Paid research study {i:03d}",
            company=f"Studio {i:03d}",
            location="Los Angeles, CA",
            state_codes=",CA,",
            job_url=f"https://example.com/study/{i}",
            source="Respondent",
            description=_LONG_DESCRIPTION,
            vertical="think",
            is_rolling=True,
            date_found=now - timedelta(minutes=i),
            last_seen_at=now,
        )
        for i in range(_MAX_RESULTS + 10)
    ])
    db.commit()

    result = search_side_quests(db, page_size=_MAX_RESULTS)
    assert result["result_count"] == _MAX_RESULTS
    size = len(json.dumps(result))
    assert size <= _MCP_RESULT_CHAR_BUDGET, (
        f"a full quest page serializes to {size:,} chars, over the "
        f"{_MCP_RESULT_CHAR_BUDGET:,} budget"
    )
    db.close()


def test_list_rows_keep_enough_text_to_triage():
    """Trimming the excerpt must not strip the ranking signal entirely."""
    from app.models.application import ApplicationRecord
    from app.services.local_agent_service import _candidate_payload

    payload = _candidate_payload(
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company="Acme",
            description=_LONG_DESCRIPTION,
        )
    )
    excerpt = payload["description_excerpt"]
    assert len(excerpt) >= 120, "too short to judge a posting from the list"
    assert "data platform leader" in excerpt


def test_detail_view_still_serves_the_long_excerpt():
    """One finalist at a time can afford the full text; a page of 50 cannot."""
    from app.models.application import ApplicationRecord
    from app.services.local_agent_service import (
        _EXCERPT_CHARS,
        _candidate_payload,
    )

    record = ApplicationRecord(
        job_title="Data Engineering Manager",
        company="Acme",
        description=_LONG_DESCRIPTION,
    )
    detail = _candidate_payload(record, detail=True)["description_excerpt"]
    listed = _candidate_payload(record)["description_excerpt"]

    assert len(detail) > len(listed)
    assert len(detail) <= _EXCERPT_CHARS + 1  # ceiling plus the ellipsis
