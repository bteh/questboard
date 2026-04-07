from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
if BACKEND_PATH in sys.path:
    sys.path.remove(BACKEND_PATH)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class AlembicMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "MANAGE_SCHEMA_ON_STARTUP": os.environ.get("MANAGE_SCHEMA_ON_STARTUP"),
        }
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-alembic-test-")
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

    def test_alembic_upgrade_creates_schema_and_startup_does_not_mutate(self) -> None:
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")

        engine = create_engine(self.database_url)
        inspector = inspect(engine)
        before_tables = set(inspector.get_table_names())
        self.assertIn("profiles", before_tables)
        self.assertIn("workspace_memberships", before_tables)
        self.assertIn("workspace_search_runs", before_tables)
        self.assertIn("file_assets", before_tables)

        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)
        backend_db = importlib.import_module("app.models.database")
        backend_db.init_db(self.database_url)

        engine = create_engine(self.database_url)
        after_tables = set(inspect(engine).get_table_names())
        self.assertEqual(before_tables, after_tables)


if __name__ == "__main__":
    unittest.main()
