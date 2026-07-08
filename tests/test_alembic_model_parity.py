"""Alembic head must match Base.metadata exactly.

tests/test_alembic.py only compares table names, so a model change without an
alembic revision used to ship green and then fail hosted at the first ORM
SELECT naming the missing column. This test upgrades a temp DB to head and
asserts an EMPTY autogenerate diff against the model metadata, which makes
any future model-without-revision change fail the suite.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
if BACKEND_PATH in sys.path:
    sys.path.remove(BACKEND_PATH)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class AlembicModelParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "MANAGE_SCHEMA_ON_STARTUP": os.environ.get("MANAGE_SCHEMA_ON_STARTUP"),
        }
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-alembic-parity-")
        self.db_path = os.path.join(self.temp_dir, "hosted.db")
        self.database_url = f"sqlite:///{self.db_path}"
        os.environ["DATABASE_URL"] = self.database_url
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "false"

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_alembic_head_matches_model_metadata(self) -> None:
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")

        # Fresh model imports, mirroring what env.py registers on Base.metadata.
        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)
        backend_db = importlib.import_module("app.models.database")
        importlib.import_module("app.models.application")
        importlib.import_module("app.models.rate_limit")
        importlib.import_module("app.models.workspace")

        engine = create_engine(self.database_url)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            diffs = compare_metadata(ctx, backend_db.Base.metadata)

        self.assertEqual(
            diffs,
            [],
            msg=(
                "Model metadata and alembic head disagree. A model changed "
                "without a migration (or a revision drifted from the model). "
                "Add an alembic revision that closes this diff:\n"
                + "\n".join(repr(d) for d in diffs)
            ),
        )


if __name__ == "__main__":
    unittest.main()
