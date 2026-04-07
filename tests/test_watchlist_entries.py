from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import watchlist_service


class WatchlistEntriesTest(unittest.TestCase):
    def test_build_watchlist_entries_only_keeps_confirmed_ats(self) -> None:
        discovered = {
            "OpenAI": {
                "name": "OpenAI",
                "slug": "openai",
                "ats": "greenhouse",
                "job_count": 12,
                "careers_url": "https://boards.greenhouse.io/openai",
            },
            "Unknown Co": {
                "name": "Unknown Co",
                "slug": "unknown-co",
                "ats": "unknown",
                "job_count": 0,
                "careers_url": "",
            },
        }

        with patch.object(
            watchlist_service,
            "discover_company",
            side_effect=lambda name: discovered[name],
        ):
            entries = watchlist_service.build_watchlist_entries(
                ["OpenAI", "Unknown Co", "OpenAI"],
            )

        self.assertEqual(
            entries,
            [
                {
                    "name": "OpenAI",
                    "slug": "openai",
                    "ats": "greenhouse",
                    "job_count": 12,
                    "careers_url": "https://boards.greenhouse.io/openai",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
