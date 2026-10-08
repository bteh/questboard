"""r/castingcalls (perform kind) via arctic-shift.

Board content under the owner's 2026-10-08 carve-out (BOARD_SUBREDDITS in
_reddit.py). The sub mixes real casting calls with actors promoting
themselves, questions about casting studios, and ads for casting-call
sites. A row needs a casting ask in its title ("casting", "auditions",
"actors needed", "seeking a voice actor"); bodies are too noisy to gate
on. Self-promo and question titles are dropped. Calls that say they are unpaid are dropped:
this board lists paid quests.

Location is set only when the post names a place; most calls are not in
Los Angeles and none is assumed.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._reddit import (
    ARCTIC_API_URL,
    HOUSE_RULES_RE,
    THREAD_PREFIX,
    UNPAID_RE,
    arctic_params,
    author_handle,
    clean_body,
    extract_pay,
    is_removed,
    older_than,
    research_only_for,
    stated_place,
)
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date, _strip_html

logger = logging.getLogger(__name__)

SUBREDDIT = "castingcalls"

_TALENT = (
    r"(?:actors?|actress(?:es)?|voice ?actors?|voice talent|vas?|extras?|background"
    r"|models?|hosts?|performers?|singers?|dancers?|musicians?|talent|cast|leads?|roles?)"
)

_CASTING_RE = re.compile(
    r"\bcasting\b|\bauditions?\b|\bnow casting\b"
    rf"|\b{_TALENT}\b.{{0,30}}\b(?:needed|wanted|search)\b"
    rf"|\b(?:seeking|looking for|need|needs|searching for|hiring)\b.{{0,30}}\b{_TALENT}\b",
    re.IGNORECASE,
)

_NOT_A_CALL_RE = re.compile(
    r"hire me|\bfor hire\b|\blooking for (?:a |any )?(?:role|acting|opportunit|work)"
    r"|\bmy (?:reel|demo)\b|\bfeedback\b|\bheadshots?\b|\bnew to va\b"
    r"|^(?:has|have|does|did|is|are|anyone|how|what|why|where|should)\b"
    r"|\bcasting calls? in seconds\b|\bcasting calls? this week\b|\bwebsite\b",
    re.IGNORECASE,
)

_DEFAULT_MAX_DAYS = 30


def _is_call(title: str) -> bool:
    if _NOT_A_CALL_RE.search(title):
        return False
    return bool(_CASTING_RE.search(title))


def _normalize_post(post: dict) -> dict | None:
    """Map one arctic-shift post to a perform-kind row, or None."""
    title = re.sub(r"\s+", " ", post.get("title") or "").strip()
    url = post.get("url") or ""
    if not title or not url.startswith(THREAD_PREFIX) or is_removed(post):
        return None

    body = clean_body(post)
    text = f"{title}\n{body}"
    if HOUSE_RULES_RE.search(text) or UNPAID_RE.search(text):
        return None
    if not _is_call(title):
        return None

    pay_note, salary_fields = extract_pay(title, body)
    place = stated_place(title, body) or ""
    row: dict = {
        "title": title,
        "company": author_handle(post, f"r/{SUBREDDIT}"),
        "location": place,
        "is_remote": place == "Remote",
        "url": url,
        "source": "reddit-castingcalls",
        "vertical": "perform",
        "description": _strip_html(body) if body else "",
        **salary_fields,
    }
    if pay_note:
        row["quest"] = {"pay_note": pay_note}
    posted = _parse_posted_date(post.get("created_utc"))
    if posted is not None:
        row["date_posted"] = posted.isoformat()
    return row


@register_scraper(
    name="reddit-castingcalls",
    display_name="Reddit",
    url="https://www.reddit.com/r/castingcalls/",
    description="Casting calls from r/castingcalls via the arctic-shift mirror",
    category="perform",
    kind="perform",
    stale_after_days=14,
    refresh_hours=12,
    enabled_by_default=False,
    research_only=research_only_for(SUBREDDIT),
    allowed_url_hosts=("reddit.com",),
)
def search_reddit_castingcalls(
    roles: list[str] | None = None,
    max_results: int = 50,
    max_days_old: int | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch casting calls from r/castingcalls. ``roles`` is ignored."""
    data = _get_json(ARCTIC_API_URL, params=arctic_params(SUBREDDIT))
    posts = data.get("data") if isinstance(data, dict) else None
    if not isinstance(posts, list):
        return []

    days = max_days_old or _DEFAULT_MAX_DAYS
    results: list[dict] = []
    seen: set[str] = set()
    for post in posts:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict) or older_than(post, days):
            continue
        row = _normalize_post(post)
        if row is None:
            continue
        key = f"{row['company'].lower()}|{row['title'].lower()}"
        if row["url"] in seen or key in seen:
            continue
        seen.update((row["url"], key))
        results.append(row)

    logger.info("r/castingcalls: %d casting calls", len(results))
    return results
