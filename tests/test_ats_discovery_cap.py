"""ATS slug discovery must cap how many roles it fans out to DuckDuckGo.

Bug: discovery looped over the full AI-expanded role list (10-20 roles) with a
fresh sequential DDG query each, ×3 ATS hosts — up to ~60 serial network calls
on a cold/stale cache before greenhouse/lever/ashby could return anything.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import _ats_discovery


class _FakeDDGS:
    calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, max_results=10):
        type(self).calls += 1
        return []


class ATSDiscoveryCapTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeDDGS.calls = 0
        self._orig_ddgs = sys.modules.get("ddgs")
        sys.modules["ddgs"] = types.SimpleNamespace(DDGS=_FakeDDGS)

    def tearDown(self) -> None:
        if self._orig_ddgs is None:
            sys.modules.pop("ddgs", None)
        else:
            sys.modules["ddgs"] = self._orig_ddgs

    def test_discovery_caps_role_fanout(self) -> None:
        roles = [f"role number {i}" for i in range(15)]
        host = next(iter(_ats_discovery.ATS_HOSTS))  # any valid host
        _ats_discovery.discover_slugs(host, roles)
        # One DDG query per role — must be capped well below the 15 supplied.
        self.assertLessEqual(_FakeDDGS.calls, 6)
        self.assertGreater(_FakeDDGS.calls, 0)

    def test_discovery_respects_explicit_max_roles(self) -> None:
        roles = [f"role number {i}" for i in range(15)]
        host = next(iter(_ats_discovery.ATS_HOSTS))
        _ats_discovery.discover_slugs(host, roles, max_roles=3)
        self.assertEqual(_FakeDDGS.calls, 3)


if __name__ == "__main__":
    unittest.main()
