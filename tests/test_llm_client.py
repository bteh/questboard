from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, SRC_PATH)

from job_finder.llm_client import _parse_loose_json


class LooseJsonParsingTest(unittest.TestCase):
    def test_extracts_partial_string_arrays_from_truncated_json(self) -> None:
        raw = """{
  "roles": [
    "Director, Data Platform",
    "Lead Data Platform Engineer"
  ],
  "keywords": [
    "dbt",
    "lakehouse"
  ],
  "companies": [
    "Databricks",
    "Snowflake"
"""

        parsed = _parse_loose_json(raw)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["roles"], ["Director, Data Platform", "Lead Data Platform Engineer"])
        self.assertEqual(parsed["keywords"], ["dbt", "lakehouse"])
        self.assertEqual(parsed["companies"], ["Databricks", "Snowflake"])


if __name__ == "__main__":
    unittest.main()
