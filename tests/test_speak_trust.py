"""Speak-lane trust guards: no predatory conferences, no fake deadlines.

Both cases were confirmed on the live board by the 2026-07-12 accuracy
audit: a Paris "4th Tech Summit on AI & Robotics" on averconferences.com
(a pay-to-present mill) and a "Web3 London" CFP whose 2050-01-01 close is
a rolling-call placeholder, not a real deadline.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._speak import (  # noqa: E402
    is_predatory_host,
    is_sentinel_deadline,
)


class TestPredatoryHost:
    def test_the_confirmed_mill_and_subdomains(self) -> None:
        assert is_predatory_host("https://artificialintelligence.averconferences.com/x.php")
        assert is_predatory_host("https://averconferences.com/summit")

    def test_other_documented_mills(self) -> None:
        assert is_predatory_host("https://waset.org/conference")
        assert is_predatory_host("https://www.omicsonline.org/cfp")

    def test_real_conference_hosts_pass(self) -> None:
        assert not is_predatory_host("https://sessionize.com/devfest-milano-2026")
        assert not is_predatory_host("https://www.papercall.io/conf42")
        assert not is_predatory_host("https://gitnation.com/ai-coding-summit")


class TestSentinelDeadline:
    def test_placeholder_far_future(self) -> None:
        assert is_sentinel_deadline(datetime(2050, 1, 1, tzinfo=timezone.utc))
        assert is_sentinel_deadline(datetime(9999, 12, 31))

    def test_real_deadlines_are_fine(self) -> None:
        assert not is_sentinel_deadline(datetime(2026, 9, 1, tzinfo=timezone.utc))
        assert not is_sentinel_deadline(datetime(2027, 12, 31))


class TestCallingAllPapersRejectsPredatory:
    def setUp_mod(self):
        from job_finder.tools.scrapers import callingallpapers as mod
        return mod

    def test_predatory_uri_is_unacceptable(self) -> None:
        mod = self.setUp_mod()
        assert mod._acceptable_uri("https://sessionize.com/real-conf") is True
        assert mod._acceptable_uri("https://ai.averconferences.com/scientific_session.php") is False


class TestPapercallRejectsSentinel:
    def test_sentinel_dated_card_never_publishes(self) -> None:
        from bs4 import BeautifulSoup

        from job_finder.tools.scrapers import papercall as mod

        # a card with a 2050 close time, otherwise well-formed
        html = """
        <div class="event-list-detail">
          <h3 class="event__title"><a href="/web3-london">Web3 London</a></h3>
          <var class="atc_title">Web3 London</var>
          <var class="atc_location">London, UK</var>
          <time datetime="2050-01-01T00:00:00Z">Jan 01, 2050</time>
        </div>"""
        card = BeautifulSoup(html, "html.parser").select_one("div.event-list-detail")
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        assert mod._normalize_card(card, now) is None
