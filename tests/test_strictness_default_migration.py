"""The strictness-default normalization migration.

Bug: b3f1c8a5e210 added match_strictness with server_default='loose' and
backfilled existing rows to 'loose', so returning users searched with 'loose'
even though the product default is now 'balanced'. A follow-up migration must
reset those legacy 'loose'/NULL/'' rows to 'balanced' (while preserving an
explicit 'strict' choice).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for p in (BACKEND_PATH, SRC_PATH):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

_PREV_REVISION = "b3f1c8a5e210"  # add match_strictness (server_default loose)


class StrictnessDefaultMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "MANAGE_SCHEMA_ON_STARTUP": os.environ.get("MANAGE_SCHEMA_ON_STARTUP"),
        }
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-strictness-test-")
        self.db_path = os.path.join(self.temp_dir, "hosted.db")
        self.database_url = f"sqlite:///{self.db_path}"
        os.environ["DATABASE_URL"] = self.database_url
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "false"
        self.config = Config(str(ROOT / "alembic.ini"))

    def tearDown(self) -> None:
        for key, value in self._orig.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_loose_rows_become_balanced_strict_preserved(self) -> None:
        # Bring the schema up to the point the strictness column exists.
        command.upgrade(self.config, _PREV_REVISION)
        engine = create_engine(self.database_url)
        with engine.begin() as conn:
            # A legacy row backfilled to 'loose', plus NULL/'' variants, and an
            # explicit 'strict' choice that must survive.
            conn.execute(text(
                "INSERT INTO workspace_preferences (workspace_id, match_strictness) "
                "VALUES ('ws-loose', 'loose'), ('ws-null', NULL), "
                "('ws-empty', ''), ('ws-strict', 'strict')"
            ))

        # Run the remaining migrations (the normalization).
        command.upgrade(self.config, "head")

        with engine.connect() as conn:
            rows = dict(
                conn.execute(text(
                    "SELECT workspace_id, match_strictness FROM workspace_preferences"
                )).all()
            )
        self.assertEqual(rows["ws-loose"], "balanced")
        self.assertEqual(rows["ws-null"], "balanced")
        self.assertEqual(rows["ws-empty"], "balanced")
        self.assertEqual(rows["ws-strict"], "strict")  # explicit choice preserved


if __name__ == "__main__":
    unittest.main()
