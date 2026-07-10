"""Rotating SQLite snapshots: the local backup plan.

Pins: a snapshot lands next to the live DB and actually contains the
data, rotation prunes to the cap, the interval skips fresh re-snapshots,
and failure never raises (a refresh must not die because a backup did).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, SRC_PATH)


@pytest.fixture()
def db(tmp_path):
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(tmp_path / "live.db"))
    jf_db.save_application(
        job_title="Snapshot me", company="Fixture", job_url="https://x.example/1"
    )
    yield jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def test_snapshot_contains_the_data_and_rotates(db, tmp_path):
    from job_finder.backup import snapshot_database

    first = snapshot_database(min_interval_hours=0)
    assert first is not None and first.exists()
    with sqlite3.connect(first) as conn:
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    assert count == 1

    # rotation keeps only the newest max_keep snapshots
    for _ in range(4):
        assert snapshot_database(min_interval_hours=0, max_keep=3) is not None
    left = sorted((tmp_path / "backups").glob("live-*.db"))
    assert len(left) == 3


def test_interval_skips_a_fresh_snapshot(db):
    from job_finder.backup import snapshot_database

    assert snapshot_database(min_interval_hours=0) is not None
    assert snapshot_database(min_interval_hours=20) is None


def test_backup_failure_never_raises(db, monkeypatch):
    import job_finder.backup as backup

    monkeypatch.setattr(backup, "_live_sqlite_path", lambda: (_ for _ in ()).throw(RuntimeError))
    assert backup.snapshot_database() is None
