"""HN 'Who is hiring?' scraper: every published row links somewhere real (the
poster's URL, else the HN comment permalink), and paragraph/URL 'titles' are
dropped rather than shipped as garbage."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from job_finder.tools.scrapers import hackernews as mod  # noqa: E402

_MONTH = datetime.now(timezone.utc).strftime("%B %Y")

# id 111: clean role, no URL in the post  -> link falls back to the HN permalink
# id 222: clean role, a real apply URL    -> link is that URL
# id 333: no clean role, a URL + paragraph -> dropped (garbage title)
_COMMENTS = [
    {"id": 111, "created_at": "2026-07-01T00:00:00Z",
     "text": "Acme | Senior Engineer | Remote | Email jobs@acme.example to apply"},
    {"id": 222, "created_at": "2026-07-01T00:00:00Z",
     "text": "Beta Inc | Staff Data Engineer | Remote | https://beta.example/careers"},
    {"id": 333, "created_at": "2026-07-01T00:00:00Z",
     "text": ("Gamma | https://gamma.example Repeat founder building something new and "
              "putting together a founding team, this is a long paragraph well over ninety chars")},
]


def _fake_get_json(url, params=None):
    if "/items/" in url:
        return {"children": _COMMENTS}
    return {"hits": [{"title": f"Ask HN: Who is hiring? ({_MONTH})", "objectID": "thread1"}]}


class HackerNewsScraperTest(unittest.TestCase):
    def _run(self):
        with patch.object(mod, "_get_json", side_effect=_fake_get_json):
            return mod.search_hn_hiring(roles=["engineer"])

    def test_no_row_has_an_empty_link(self):
        rows = self._run()
        self.assertTrue(rows)
        for r in rows:
            self.assertTrue(r["url"].startswith("http"), r)

    def test_url_falls_back_to_hn_permalink(self):
        by_co = {r["company"]: r for r in self._run()}
        self.assertEqual(by_co["Acme"]["url"], "https://news.ycombinator.com/item?id=111")

    def test_real_apply_url_is_kept(self):
        by_co = {r["company"]: r for r in self._run()}
        self.assertEqual(by_co["Beta Inc"]["url"], "https://beta.example/careers")

    def test_paragraph_or_url_titles_are_dropped(self):
        companies = {r["company"] for r in self._run()}
        self.assertNotIn("Gamma", companies)
        self.assertEqual(companies, {"Acme", "Beta Inc"})
