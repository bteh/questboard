"""Boot must not re-classify every saved posting.

Real case (Sep 9 2026): the packaged app took 15 to 22 seconds from launch
to a healthy API. Profiling init_db on a copy of the real database showed
15.3 of those seconds inside the schema migration's taxonomy backfill: it
selected every row whose industry_tags was '[]' and ran
classify_job_taxonomy on it. Most postings legitimately classify to no
industry, which is stored as '[]', so 14,303 rows were re-classified at
every launch, forever. Rule changes are already handled by the versioned
company_taxonomy repair in maintenance.py, which runs once per version.

Rules under test (each after one warm-up boot, so the versioned repair has
already run and only the per-boot migration is being measured):
1. A database whose taxonomy columns exist is not re-classified at boot,
   even when every row's tags are '[]'.
2. A legacy database that gains the columns during a boot is classified on
   that boot, and the next boot classifies nothing.
3. Rows whose tags are NULL (never classified) still get classified.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.models import database as db_module  # noqa: E402

ROWS = 40


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job_tracker.db'}")
    db_module.Base.metadata.create_all(engine)
    return engine


def _seed(engine) -> None:
    with engine.begin() as conn:
        for i in range(ROWS):
            conn.execute(
                text(
                    "INSERT INTO applications (job_title, company, job_url, source, vertical) "
                    "VALUES (:t, :c, :u, 'indeed', 'career')"
                ),
                {"t": f"Data Engineer {i}", "c": f"Acme {i}", "u": f"https://jobs.example/{i}"},
            )


@pytest.fixture()
def counting_classifier(monkeypatch):
    from job_finder import company_taxonomy

    calls: list[str] = []

    def fake(*_args, **kwargs):
        calls.append(str(kwargs.get("company", "")))
        return [], []

    monkeypatch.setattr(company_taxonomy, "classify_job_taxonomy", fake)
    return calls


def _boot(engine) -> None:
    db_module._migrate_db(engine)


def test_existing_database_with_empty_tags_is_not_reclassified(tmp_path, counting_classifier) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _boot(engine)
    counting_classifier.clear()

    _boot(engine)

    assert counting_classifier == []


def test_legacy_database_is_classified_when_the_columns_arrive_then_left_alone(
    tmp_path, counting_classifier
) -> None:
    if sqlite3.sqlite_version_info < (3, 35):
        pytest.skip("DROP COLUMN needs SQLite 3.35")
    engine = _engine(tmp_path)
    _seed(engine)
    _boot(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE applications DROP COLUMN industry_tags"))
        conn.execute(text("ALTER TABLE applications DROP COLUMN ecosystem_tags"))
    counting_classifier.clear()

    _boot(engine)
    assert len(counting_classifier) >= ROWS
    with engine.connect() as conn:
        untagged = conn.execute(
            text("SELECT count(*) FROM applications WHERE industry_tags IS NULL OR ecosystem_tags IS NULL")
        ).scalar()
    assert untagged == 0

    counting_classifier.clear()
    _boot(engine)
    assert counting_classifier == []


def test_rows_never_classified_still_get_classified(tmp_path, counting_classifier) -> None:
    engine = _engine(tmp_path)
    _seed(engine)
    _boot(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE applications SET industry_tags = NULL WHERE id <= 3"))
    counting_classifier.clear()

    _boot(engine)

    assert len(counting_classifier) == 3
    with engine.connect() as conn:
        untagged = conn.execute(
            text("SELECT count(*) FROM applications WHERE industry_tags IS NULL")
        ).scalar()
    assert untagged == 0
