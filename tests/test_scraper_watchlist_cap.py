"""A user-named watchlist board must never lose rows to the per-source cap.

On 2026-08-16 all four ATS sources saturated at exactly 500 rows, and the
truncation inside a relevance tier was thread-completion order. Alo Yoga,
the user's explicit company target (771 postings, a 24.9MB payload with
content), had its "Manager of Data Engineering" row cut by
``rank_by_relevance(results, roles)[:max_results]``. The fix: rows fetched
from a watchlist board are flagged and the shared cap helper
(``cap_with_protected`` in _utils.py) lets them through the cap. Watchlist
boards also get a 30s HTTP timeout (Alo's 24.9MB payload can blow the 5s
default), and a watchlist board whose fetch fails entirely is logged at
WARNING, because a user-named company silently missing is the exact failure
this exists to kill.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

ROLES = ["data engineer"]
PROTECTED_KEY = "_watchlist_protected"

NEW_ISO = "2026-08-10T00:00:00Z"
OLD_ISO = "2026-05-01T00:00:00Z"


def _epoch_ms(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _gh_payload(rows: list[tuple[str, str]]) -> dict:
    return {"jobs": [
        {
            "title": title,
            "absolute_url": f"https://boards.greenhouse.io/x/{i}",
            "location": {"name": "Los Angeles, CA"},
            "content": "",
            "first_published": date,
            "updated_at": date,
        }
        for i, (title, date) in enumerate(rows)
    ]}


def _lever_payload(rows: list[tuple[str, str]]) -> list:
    return [
        {
            "text": title,
            "hostedUrl": f"https://jobs.lever.co/x/{i}",
            "categories": {"location": "Los Angeles, CA"},
            "descriptionPlain": "a role",
            "createdAt": _epoch_ms(date),
            "workplaceType": "onsite",
        }
        for i, (title, date) in enumerate(rows)
    ]


def _ashby_payload(rows: list[tuple[str, str]]) -> dict:
    return {"jobs": [
        {
            "title": title,
            "jobUrl": f"https://jobs.ashbyhq.com/x/{i}",
            "descriptionPlain": "a role",
            "location": "Los Angeles, CA",
            "isRemote": False,
            "workplaceType": "Onsite",
            "publishedAt": date,
        }
        for i, (title, date) in enumerate(rows)
    ]}


def _workable_payload(rows: list[tuple[str, str]]) -> dict:
    return {"name": "X", "jobs": [
        {
            "title": title,
            "url": f"https://apply.workable.com/x/j/{i}",
            "city": "Los Angeles",
            "country": "US",
            "telecommuting": False,
            "description": "a role",
            "published_on": date,
        }
        for i, (title, date) in enumerate(rows)
    ]}


# (module name, search fn, payload builder, default per-board timeout)
SOURCES = [
    ("greenhouse", "search_greenhouse", _gh_payload, 5),
    ("lever", "search_lever", _lever_payload, 5),
    ("ashby", "search_ashby", _ashby_payload, 5),
    ("workable", "search_workable", _workable_payload, 6),
]

SEED_ROWS = [
    ("Data Engineer", NEW_ISO),
    ("Senior Data Engineer", NEW_ISO),
    ("Staff Data Engineer", NEW_ISO),
]
ALO_ROWS = [("Manager of Data Engineering", OLD_ISO)]


def _module(name: str):
    import importlib
    return importlib.import_module(f"job_finder.tools.scrapers.{name}")


class CapWithProtectedTest(unittest.TestCase):
    """Helper-level pin of the real 2026-08-16 truncation."""

    def test_watchlist_board_rows_survive_500_cap_aloyoga(self):
        from job_finder.tools.scrapers._utils import (
            PROTECTED_ROW_KEY,
            cap_with_protected,
        )
        filler = [
            {
                "title": "Senior Data Engineer",
                "company": f"Seed {i:03d}",
                "url": f"https://boards.greenhouse.io/seed{i}/1",
                "date_posted": NEW_ISO,
            }
            for i in range(500)
        ]
        alo = {
            "title": "Manager of Data Engineering",
            "company": "Alo Yoga",
            "url": "https://boards.greenhouse.io/aloyoga/771",
            "date_posted": OLD_ISO,
            PROTECTED_ROW_KEY: True,
        }
        capped = cap_with_protected(filler + [alo], ROLES, 500)
        self.assertEqual(len(capped), 501)
        self.assertIn("Alo Yoga", [r["company"] for r in capped])
        self.assertTrue(all(PROTECTED_ROW_KEY not in r for r in capped))

    def test_a_protected_row_inside_the_cap_is_not_duplicated(self):
        from job_finder.tools.scrapers._utils import (
            PROTECTED_ROW_KEY,
            cap_with_protected,
        )
        alo = {
            "title": "Data Engineer",
            "company": "Alo Yoga",
            "url": "https://boards.greenhouse.io/aloyoga/1",
            "date_posted": NEW_ISO,
            PROTECTED_ROW_KEY: True,
        }
        filler = [
            {
                "title": "Data Engineer",
                "company": f"Seed {i}",
                "url": f"https://boards.greenhouse.io/seed{i}/1",
                "date_posted": OLD_ISO,
            }
            for i in range(5)
        ]
        capped = cap_with_protected([alo] + filler, ROLES, 3)
        self.assertEqual(len(capped), 3)
        self.assertEqual(
            [r["company"] for r in capped].count("Alo Yoga"), 1
        )

    def test_without_protected_rows_the_cap_is_unchanged(self):
        from job_finder.tools.scrapers._utils import cap_with_protected
        rows = [
            {
                "title": "Data Engineer",
                "company": f"Seed {i}",
                "url": f"https://x/{i}",
                "date_posted": NEW_ISO,
            }
            for i in range(10)
        ]
        self.assertEqual(len(cap_with_protected(rows, ROLES, 4)), 4)


class WatchlistScraperIntegrationTest(unittest.TestCase):
    """All four ATS scrapers honor the watchlist exemption end to end."""

    def _run(self, mod, fn_name, payload_fn, max_results=3):
        def fake_get_json(url, params=None, **kwargs):
            if "aloyoga" in url:
                return payload_fn(ALO_ROWS)
            return payload_fn(SEED_ROWS)

        with patch.object(mod, "ATS_FETCH_WORKERS", 1), \
                patch.object(mod, "_get_json", side_effect=fake_get_json):
            return getattr(mod, fn_name)(
                roles=ROLES,
                max_results=max_results,
                companies=["seedco"],
                watchlist_companies=["aloyoga"],
            )

    def test_watchlist_rows_survive_the_source_cap_aloyoga(self):
        """Seed rows are newer and same tier, so without the exemption the
        watchlist row is deterministically the one the cap cuts."""
        for name, fn_name, payload_fn, _ in SOURCES:
            with self.subTest(source=name):
                mod = _module(name)
                rows = self._run(mod, fn_name, payload_fn)
                titles = [r["title"] for r in rows]
                self.assertIn("Manager of Data Engineering", titles)

    def test_watchlist_rows_do_not_leak_the_internal_flag(self):
        for name, fn_name, payload_fn, _ in SOURCES:
            with self.subTest(source=name):
                mod = _module(name)
                rows = self._run(mod, fn_name, payload_fn)
                self.assertTrue(
                    all(PROTECTED_KEY not in r for r in rows)
                )

    def test_watchlist_board_gets_30s_timeout_for_aloyoga_24mb_payload(self):
        for name, fn_name, payload_fn, default_timeout in SOURCES:
            with self.subTest(source=name):
                mod = _module(name)
                seen: dict[str, object] = {}

                def fake_get_json(url, params=None, **kwargs):
                    slug = "aloyoga" if "aloyoga" in url else "seedco"
                    seen[slug] = kwargs.get("timeout")
                    return payload_fn(SEED_ROWS)

                with patch.object(mod, "ATS_FETCH_WORKERS", 1), \
                        patch.object(mod, "_get_json", side_effect=fake_get_json):
                    getattr(mod, fn_name)(
                        roles=ROLES,
                        max_results=500,
                        companies=["seedco"],
                        watchlist_companies=["aloyoga"],
                    )
                self.assertEqual(seen["aloyoga"], 30)
                self.assertEqual(seen["seedco"], default_timeout)

    def test_failed_watchlist_board_fetch_logs_a_warning(self):
        """A user-named company silently missing is the failure mode this
        whole fix exists to kill."""
        for name, fn_name, payload_fn, _ in SOURCES:
            with self.subTest(source=name):
                mod = _module(name)

                def fake_get_json(url, params=None, **kwargs):
                    if "aloyoga" in url:
                        return None
                    return payload_fn(SEED_ROWS)

                with patch.object(mod, "ATS_FETCH_WORKERS", 1), \
                        patch.object(mod, "_get_json", side_effect=fake_get_json):
                    with self.assertLogs(mod.logger, level="WARNING") as logs:
                        getattr(mod, fn_name)(
                            roles=ROLES,
                            max_results=500,
                            companies=["seedco"],
                            watchlist_companies=["aloyoga"],
                        )
                self.assertTrue(
                    any("aloyoga" in line for line in logs.output)
                )


if __name__ == "__main__":
    unittest.main()
