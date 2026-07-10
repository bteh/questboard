"""r/PKMNTCGDeals (flip kind): live TCG drops and restocks via arctic-shift.

The flip community's supply signal: "Walmart Wednesday 9PM EST", "Target
drop happening NOW", with product details and sometimes stock estimates.
Only ACTIVE-flaired posts are ingested; the flair is the sub's own
moderation verdict that a drop is real and live, and it filters the
unflaired resale spam in one move.

Pay is deliberately NEVER emitted for this source: a "$" in a drop post
is a retail PRICE (what you pay), not a payout, and mapping it to the
reward slot would lie. The reward tab renders "not stated", which is the
truth of a flip lead.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._reddit import (
    ARCTIC_API_URL,
    THREAD_PREFIX,
    arctic_params,
    author_handle,
    clean_body,
)
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date, _strip_html

logger = logging.getLogger(__name__)


def _is_active_drop(post: dict) -> bool:
    return (post.get("link_flair_text") or "").strip().lower() == "active"


def _normalize_post(post: dict) -> dict | None:
    """Map one arctic-shift post to a flip-kind quest row, or None."""
    title = re.sub(r"\s+", " ", post.get("title") or "").strip()
    url = post.get("url") or ""
    if not title or not url.startswith(THREAD_PREFIX):
        return None

    body = clean_body(post)
    row: dict = {
        "title": title,
        "company": author_handle(post, "r/PKMNTCGDeals"),
        "location": "",
        "url": url,
        "source": "reddit-pkmntcgdeals",
        "vertical": "flip",
        "description": _strip_html(body) if body else "",
    }
    posted = _parse_posted_date(post.get("created_utc"))
    if posted is not None:
        row["date_posted"] = posted.isoformat()
    return row


@register_scraper(
    name="reddit-pkmntcgdeals",
    display_name="r/PKMNTCGDeals (drops & restocks)",
    url="https://www.reddit.com/r/PKMNTCGDeals/",
    description="Mod-verified ACTIVE TCG drops and restocks via the arctic-shift mirror",
    category="flip",
    kind="flip",
    # drops happen the same night; two days later the lead is dead
    stale_after_days=2,
    enabled_by_default=False,
    # curation verdict 2026-07-10: a reddit thread about a drop is not a
    # place to act; the flip lane is paused until sanctioned retailer
    # sources + the scheduler exist (see docs/source-coverage.md)
    research_only=True,
)
def search_reddit_pkmntcgdeals(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch ACTIVE drop/restock posts from r/PKMNTCGDeals via arctic-shift.

    ``roles`` is ignored on purpose. Drops age fast; date_posted is exact
    on every row so freshness handling stays downstream.
    """
    logger.info("Fetching ACTIVE drops from r/PKMNTCGDeals...")
    data = _get_json(ARCTIC_API_URL, params=arctic_params("PKMNTCGDeals"))
    posts = data.get("data") if isinstance(data, dict) else None
    if not isinstance(posts, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for post in posts:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict) or not _is_active_drop(post):
            continue
        row = _normalize_post(post)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("r/PKMNTCGDeals: %d active drops", len(results))
    return results
