"""r/slavelabour (odd kind): paid [Task] posts via arctic-shift.

The sub splits into [Task] (someone paying for a one-off) and [Offer]
(someone selling their labor); only [Task] posts are quests. Pay is
usually stated right in the title ("[Task] Easy $30") and is extracted by
the shared stated-pay rules, never inferred.

Ingest guardrails, from the sub's own scam-alert history: tasks that buy
platform manipulation (karma, upvotes, votes, reviews) or pay in gift
cards are skipped. They are real posts, but they fail the board's house
rules ("If it's pinned here, it's real" cuts both ways).

Automod closes filled tasks by removing the body; titles, flair, and
dates persist, so rows are kept with an empty description rather than a
"[removed]" placeholder.
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
    extract_pay,
)
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date, _strip_html

logger = logging.getLogger(__name__)

# platform-manipulation and gift-card tasks fail the house rules
_EXCLUDE_RE = re.compile(
    r"gift ?cards?|\bkarma\b|\bupvotes?\b|\bdownvotes?\b|vote for|\breviews? for\b",
    re.IGNORECASE,
)


def _is_task(post: dict) -> bool:
    flair = (post.get("link_flair_text") or "").strip().lower()
    if flair:
        return flair == "task"
    return (post.get("title") or "").lower().startswith("[task]")


def _normalize_post(post: dict) -> dict | None:
    """Map one arctic-shift post to an odd-kind quest row, or None."""
    title = re.sub(r"\s+", " ", post.get("title") or "").strip()
    url = post.get("url") or ""
    if not title or not url.startswith(THREAD_PREFIX):
        return None

    body = clean_body(post)
    if _EXCLUDE_RE.search(title) or _EXCLUDE_RE.search(body):
        return None

    description = _strip_html(body) if body else ""
    pay_note, salary_fields = extract_pay(title, body)
    quest: dict = {}
    if pay_note:
        quest["pay_note"] = pay_note

    row: dict = {
        "title": title,
        "company": author_handle(post, "r/slavelabour"),
        # tasks are online unless the post says otherwise; the one reliable
        # structured signal is a remote mention
        "location": "Remote" if re.search(r"\bremote\b", title.lower()) else "",
        "url": url,
        "source": "reddit-slavelabour",
        "vertical": "odd",
        "description": description,
        **salary_fields,
    }
    if quest:
        row["quest"] = quest
    posted = _parse_posted_date(post.get("created_utc"))
    if posted is not None:
        row["date_posted"] = posted.isoformat()
    return row


@register_scraper(
    name="reddit-slavelabour",
    display_name="r/slavelabour (paid tasks)",
    url="https://www.reddit.com/r/slavelabour/",
    description="Paid [Task] one-offs from r/slavelabour via the arctic-shift mirror",
    category="odd",
    kind="odd",
    enabled_by_default=False,
)
def search_reddit_slavelabour(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch paid [Task] posts from r/slavelabour via arctic-shift.

    ``roles`` is ignored on purpose: tasks are not career titles. The
    [Task] flair plus the manipulation filter is the gate.
    """
    logger.info("Fetching paid [Task] posts from r/slavelabour...")
    data = _get_json(ARCTIC_API_URL, params=arctic_params("slavelabour"))
    posts = data.get("data") if isinstance(data, dict) else None
    if not isinstance(posts, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for post in posts:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict) or not _is_task(post):
            continue
        row = _normalize_post(post)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("r/slavelabour: %d paid tasks", len(results))
    return results
