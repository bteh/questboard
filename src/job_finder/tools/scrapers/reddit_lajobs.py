"""r/LAjobs (odd kind, casting rows go to perform) via arctic-shift.

Board content under the owner's 2026-10-08 carve-out (BOARD_SUBREDDITS in
_reddit.py). The sub has no flairs, so the hiring side is told apart from
the job-seeking side by the post's own words: a row needs a hiring
statement ("[Hiring]", "we're looking for", "line cooks wanted") and a
title that isn't someone asking for work. Salaried career roles (a stated
yearly figure, manager/engineer titles) belong in Find Work, not here.

Posts whose body snapshotted as [removed] are dropped: on a sub with no
other gate, a mod removal is the one scam signal the mirror can see.
Location defaults to Los Angeles unless the post names somewhere else.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._reddit import (
    ARCTIC_API_URL,
    HOUSE_RULES_RE,
    LA_LABEL,
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

SUBREDDIT = "LAjobs"

_SEEKER_TITLE_RE = re.compile(
    r"for hire|hire me|\bresume\b|please help|\?"
    r"|\blooking for\b[^|]{0,40}?\b(?:work|jobs?|positions?|roles?|opportunit\w*|help|leads|career)\b"
    r"|\bseeking (?:part|full|work|a job|jobs?|employment)"
    r"|\b(?:need|find|get) (?:a |some |one )?(?:[\w-]+ )?(?:job|work)\b"
    r"|\bneed (?:night|weekend)|\bi am a\b|\bi'?m a\b|^iso\b|\blf (?:work|job)"
    r"|\brecs\b|\bscam\b|^[FM]\d\d\b",
    re.IGNORECASE,
)

# The title may say it loosely ("Truck Driver needed"); the body only
# counts when it speaks as the employer.
_TITLE_HIRING_RE = re.compile(
    r"\[hiring\]|\bhiring\b|\b(?:wanted|needed)\b|\bjob offer\b|\bjob openings?\b"
    r"|\bone[- ]time job\b|\bis looking for\b|\$\d+(?:\.\d+)?\+?\s*/\s*(?:hr|hour)",
    re.IGNORECASE,
)
_BODY_HIRING_RE = re.compile(
    r"\[hiring\]|\bnow hiring\b|\b(?:we|we're|we’re|we are|is) hiring\b"
    r"|\bwe(?:'re|’re| are) (?:looking for|seeking|recruiting)\b"
    r"|\blooking to (?:hire|fill)\b|\bpay is \$|\$\d+(?:\.\d+)?\+?\s*/\s*(?:hr|hour)",
    re.IGNORECASE,
)

_CAREER_TITLE_RE = re.compile(
    r"\b(?:manager|engineer|developer|analyst|director|specialist|coordinator"
    r"|nurse|rn|accountant|administrator|executive)\b",
    re.IGNORECASE,
)

_PERFORM_TITLE_RE = re.compile(
    r"\bactors?\b|\bactress(?:es)?\b|casting|audition|\bextras?\b|background talent"
    r"|on-camera|\bmodels?\b|voice ?over|\bhost\b|\bperformers?\b|\bsingers?\b"
    r"|\bdancers?\b|\bmusicians?\b",
    re.IGNORECASE,
)

_HOUSING_RE = re.compile(r"\blease\b|\bsublet\b|\broommates?\b", re.IGNORECASE)

# beyond this a figure is a salary, not a shift or a gig
_MAX_GIG_PAY = 10_000

_DEFAULT_MAX_DAYS = 30


def _is_hiring(title: str, body: str) -> bool:
    if _SEEKER_TITLE_RE.search(title) and not re.search(r"\[hiring\]", title, re.I):
        return False
    return bool(_TITLE_HIRING_RE.search(title) or _BODY_HIRING_RE.search(body))


def _normalize_post(post: dict) -> dict | None:
    """Map one arctic-shift post to a quest row, or None when it isn't one."""
    title = re.sub(r"\s+", " ", post.get("title") or "").strip()
    url = post.get("url") or ""
    if not title or not url.startswith(THREAD_PREFIX) or is_removed(post):
        return None

    body = clean_body(post)
    text = f"{title}\n{body}"
    if HOUSE_RULES_RE.search(text) or UNPAID_RE.search(text) or _HOUSING_RE.search(text):
        return None
    if not _is_hiring(title, body):
        return None
    if _CAREER_TITLE_RE.search(title):
        return None

    pay_note, salary_fields = extract_pay(title, body)
    if salary_fields.get("salary_period") in ("monthly", "yearly"):
        return None
    if (salary_fields.get("salary_max") or 0) > _MAX_GIG_PAY:
        return None

    place = stated_place(title, body) or LA_LABEL
    vertical = "perform" if _PERFORM_TITLE_RE.search(title) else "odd"

    row: dict = {
        "title": title,
        "company": author_handle(post, f"r/{SUBREDDIT}"),
        "location": place,
        "is_remote": place == "Remote",
        "url": url,
        "source": "reddit-lajobs",
        "vertical": vertical,
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
    name="reddit-lajobs",
    display_name="Reddit",
    url="https://www.reddit.com/r/LAjobs/",
    description="Paid shifts, one-offs, and casting posts from r/LAjobs via the arctic-shift mirror",
    category="odd",
    kind="odd",
    stale_after_days=14,
    refresh_hours=12,
    enabled_by_default=False,
    research_only=research_only_for(SUBREDDIT),
    allowed_url_hosts=("reddit.com",),
    allowed_url_paths=("/r/LAjobs/",),
)
def search_reddit_lajobs(
    roles: list[str] | None = None,
    max_results: int = 50,
    max_days_old: int | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch hiring-side posts from r/LAjobs. ``roles`` is ignored: these
    are gigs, not career titles."""
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

    logger.info("r/LAjobs: %d hiring posts", len(results))
    return results
