"""One-time versioned repair for descriptions stored before the D1 cleaner fix.

Rows scraped before _strip_html unescaped entities (audit 2026-07-21, D1)
still carry markup as literal text: entity-encoded Greenhouse junk, literal
tags like <div class="content-intro">, data-leveltext attribute noise. The
repair re-cleans stored descriptions through the SAME cleaner the scrapers
use now, records a version marker so startup never rescans, and leaves
already-clean rows byte-identical.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from job_finder.models import database
from job_finder.models.database import ApplicationRecord

# Entity-encoded Greenhouse junk with data-leveltext attributes, as stored by
# the pre-fix cleaner when the board double-served encoded HTML.
_DIRTY_ENTITY = (
    "&lt;div class=&quot;content-intro&quot;&gt;&lt;p data-leveltext=&quot;&quot; "
    "data-font=&quot;Arial&quot; data-listid=&quot;3&quot;&gt;&lt;strong&gt;About "
    "us&lt;/strong&gt; We build data platforms.&lt;/p&gt;&lt;/div&gt;"
    "&lt;p&gt;Salary: $140k-$170k&lt;/p&gt;"
)

# What the old strip-before-unescape bug actually left in most rows: the
# entities got unescaped LAST, so literal tags survived as text.
_DIRTY_LITERAL = (
    '<div class="content-intro"><p data-leveltext="" data-font="Arial">'
    "<strong>About Acme</strong> We ship data tools.</p></div>"
)

# Ashby-style descriptionPlain: legitimately clean, keeps its newlines. The
# repair must never touch it (whitespace collapse would flatten paragraphs).
_CLEAN_MULTILINE = (
    "ABOUT SUNO\n\nWe're building a music platform.\n\nWhat you'll do:\n"
    "- Build pipelines\n- Ship features"
)


def _insert(description: str, url: str) -> int:
    session = database.get_session()
    try:
        record = ApplicationRecord(
            job_title="Data Engineer",
            company="Acme",
            job_url=url,
            description=description,
        )
        session.add(record)
        session.commit()
        return record.id
    finally:
        database._close_session()


def _description(row_id: int) -> str:
    session = database.get_session()
    try:
        return session.get(ApplicationRecord, row_id).description
    finally:
        database._close_session()


class DescriptionRepairTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "job_tracker.db")
        database.init_db(self.db_path)

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def test_repair_cleans_dirty_rows_and_preserves_clean_ones(self) -> None:
        from job_finder.models import maintenance

        entity_id = _insert(_DIRTY_ENTITY, "https://example.com/a")
        literal_id = _insert(_DIRTY_LITERAL, "https://example.com/b")
        clean_id = _insert(_CLEAN_MULTILINE, "https://example.com/c")
        empty_id = _insert("", "https://example.com/d")

        session = database.get_session()
        try:
            clean_updated_at = session.get(ApplicationRecord, clean_id).updated_at
        finally:
            database._close_session()

        changed = maintenance.repair_descriptions(database._engine)
        self.assertEqual(changed, 2)

        for row_id in (entity_id, literal_id):
            text = _description(row_id)
            self.assertNotIn("<", text)
            self.assertNotIn(">", text)
            self.assertNotIn("content-intro", text)
            self.assertNotIn("data-leveltext", text)
        self.assertIn("About us", _description(entity_id))
        self.assertIn("We build data platforms.", _description(entity_id))
        self.assertIn("About Acme", _description(literal_id))

        # Already-clean rows round-trip byte-identical, newlines intact,
        # and the repair never bumps updated_at (log order must not move).
        self.assertEqual(_description(clean_id), _CLEAN_MULTILINE)
        self.assertEqual(_description(empty_id), "")
        session = database.get_session()
        try:
            self.assertEqual(
                session.get(ApplicationRecord, clean_id).updated_at,
                clean_updated_at,
            )
        finally:
            database._close_session()

    def test_second_run_is_noop_and_marker_prevents_rescan(self) -> None:
        from job_finder.models import maintenance

        row_id = _insert(_DIRTY_ENTITY, "https://example.com/a")
        self.assertEqual(maintenance.repair_descriptions(database._engine), 1)
        cleaned = _description(row_id)

        # The version marker is recorded ...
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT version FROM data_repairs WHERE name = ?",
                (maintenance.DESCRIPTION_REPAIR_NAME,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], maintenance.DESCRIPTION_REPAIR_VERSION)

        # ... and it short-circuits the second run before any row is read.
        def _boom(conn):  # pragma: no cover - must never be called
            raise AssertionError("marker did not prevent a rescan")

        with patch.object(maintenance, "_scan_and_repair_descriptions", _boom):
            self.assertEqual(
                maintenance.repair_descriptions(database._engine), 0
            )
        self.assertEqual(_description(row_id), cleaned)

    def test_startup_hook_repairs_on_init_db(self) -> None:
        row_id = _insert(_DIRTY_ENTITY, "https://example.com/a")
        # Same startup path the dev backend and the desktop sidecar use:
        # init_db -> _migrate_db -> run_startup_repairs.
        database.init_db(self.db_path)
        text = _description(row_id)
        self.assertNotIn("content-intro", text)
        self.assertIn("About us", text)

    def test_cli_accepts_db_path(self) -> None:
        from job_finder.models import maintenance

        row_id = _insert(_DIRTY_ENTITY, "https://example.com/a")
        database._SessionLocal.remove()

        exit_code = maintenance.main(["--db", self.db_path])
        self.assertEqual(exit_code, 0)

        with sqlite3.connect(self.db_path) as con:
            text = con.execute(
                "SELECT description FROM applications WHERE id = ?", (row_id,)
            ).fetchone()[0]
        self.assertNotIn("content-intro", text)
        self.assertIn("About us", text)

    def test_cli_refuses_missing_db_file(self) -> None:
        from job_finder.models import maintenance

        missing = os.path.join(self.tmpdir.name, "nope.db")
        with self.assertRaises(SystemExit):
            maintenance.main(["--db", missing])
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
