"""r/forhire (lens vertical): paid [Hiring] photo/video gigs via arctic-shift.

Reddit blocks direct scraping from most IPs, so we read the sanctioned
arctic-shift mirror, which archives posts within seconds of creation::

    GET https://arctic-shift.photon-reddit.com/api/posts/search
        ?subreddit=forhire&limit=100&sort=desc&fields=...

The response is ``{"data": [...]}``, newest first. Two live-verified quirks:

- The ``fields`` param rejects ``permalink``; ``url`` is accepted and carries
  the full reddit thread URL for self posts (all r/forhire posts are self
  posts), so ``url`` IS the deep link.
- r/forhire automod removes most new posts pending review, so the mirror's
  ``selftext`` snapshot is often the placeholder "[removed]" even for gigs
  whose live thread is later restored. Those rows are kept (title, flair,
  date, and link are all real) but the placeholder never leaks into the
  description.

Pay is emitted only when the post states a figure with a '$'. Time-rated
figures ("$15/hr") and plain ranges ("$1000-$4000") become structured salary
keys; per-piece rates ("$200-250/video") stay in ``quest.pay_note`` only,
because the piece count is unknown and a structured number would mislead.
The stated string is always kept verbatim in ``quest.pay_note``.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date, _strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
# permalink is not a valid fields value on this API; url carries the thread link.
_FIELDS = "author,created_utc,link_flair_text,selftext,title,url"
_THREAD_PREFIX = "https://www.reddit.com/r/"

# Substrings "photo" and "video" also cover photograph(y), videograph(er),
# photoshoot, etc. Matched against the TITLE only: bodies are usually the
# automod placeholder, and body mentions like "video call" are false positives.
_KEYWORDS = ("photo", "video")

_REMOVED_BODIES = frozenset({"[removed]", "[deleted]"})

# One money mention: optional ~, $, amount (optional k), optional range tail,
# optional +, optional per-unit word ("/hr", "per video", "a video").
_PAY_RE = re.compile(
    r"~?\$\s*(\d[\d,]*(?:\.\d+)?)(?:\s*([kK])\b)?"
    r"(?:\s*(?:-|to)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)(?:\s*([kK])\b)?)?"
    r"(?:\s*\+)?"
    r"(?:\s*(?:/|\bper\s+|\ban?\s+)\s*([A-Za-z]+))?"
)

_TIME_PERIODS: dict[str, str] = {
    "hr": "hourly", "hour": "hourly", "hourly": "hourly",
    "day": "daily", "daily": "daily",
    "wk": "weekly", "week": "weekly", "weekly": "weekly",
    "mo": "monthly", "month": "monthly", "monthly": "monthly",
    "yr": "yearly", "year": "yearly", "yearly": "yearly", "annum": "yearly",
}


def _amount(num: str, has_k: str | None) -> float:
    val = float(num.replace(",", ""))
    return val * 1000 if has_k else val


def _extract_pay(*texts: str) -> tuple[str | None, dict]:
    """First stated pay figure across ``texts`` -> (pay_note, salary fields).

    ``pay_note`` is the matched text verbatim. Salary keys are returned only
    for unambiguous statements: a time-rated figure or a plain range. A bare
    figure ("budget is $5000") or a per-piece rate stays note-only.
    """
    for text in texts:
        if not text:
            continue
        for m in _PAY_RE.finditer(text):
            lo_s, lo_k, hi_s, hi_k, unit = m.groups()
            # No unit and a letter right after the match: a token like "$1M
            # views" or "$30ish", not a pay figure.
            if unit is None and text[m.end():m.end() + 1].isalpha():
                continue
            note = re.sub(r"\s+", " ", m.group(0)).strip()
            period = _TIME_PERIODS.get((unit or "").lower().rstrip("s"))
            piece_rate = unit is not None and period is None
            lo = _amount(lo_s, lo_k)

            fields: dict = {}
            if hi_s:
                hi = _amount(hi_s, hi_k)
                if not piece_rate and lo <= hi:
                    fields = {
                        "salary_min": lo,
                        "salary_max": hi,
                        "salary_source": "reported",
                    }
                    if period:
                        fields["salary_period"] = period
            elif period:
                fields = {
                    "salary_min": lo,
                    "salary_max": lo,
                    "salary_period": period,
                    "salary_source": "reported",
                }
            return note, fields
    return None, {}


def _is_hiring(post: dict) -> bool:
    """[Hiring] gate: the Hiring flair (live flairs carry no brackets) or an
    explicit [hiring] tag in the title. The 'For Hire' flair never matches."""
    flair = (post.get("link_flair_text") or "").lower()
    title = (post.get("title") or "").lower()
    return "hiring" in flair or "[hiring]" in title


def _normalize_post(post: dict) -> dict | None:
    """Map one arctic-shift post object to a lens-vertical quest row, or None."""
    title = re.sub(r"\s+", " ", post.get("title") or "").strip()
    url = post.get("url") or ""
    if not title or not url.startswith(_THREAD_PREFIX):
        return None

    title_lower = title.lower()
    if not any(kw in title_lower for kw in _KEYWORDS):
        return None

    author = (post.get("author") or "").strip()
    company = f"u/{author}" if author and author != "[deleted]" else "r/forhire"

    body_raw = (post.get("selftext") or "").strip()
    body = "" if body_raw in _REMOVED_BODIES else body_raw
    description = _strip_html(body) if body else ""

    pay_note, salary_fields = _extract_pay(title, body)
    quest: dict = {}
    if pay_note:
        quest["pay_note"] = pay_note

    row: dict = {
        "title": title,
        "company": company,
        # Posts carry no structured location; a "remote" mention in the title
        # is the one reliable signal.
        "location": "Remote" if re.search(r"\bremote\b", title_lower) else "",
        "url": url,
        "source": "reddit-forhire",
        "vertical": "lens",
        "description": description,
        **salary_fields,
    }
    if quest:
        row["quest"] = quest
    # created_utc is the exact posting epoch, always present in practice.
    posted = _parse_posted_date(post.get("created_utc"))
    if posted is not None:
        row["date_posted"] = posted.isoformat()
    return row


@register_scraper(
    name="reddit-forhire",
    display_name="r/forhire (photo/video gigs)",
    url="https://www.reddit.com/r/forhire/",
    description="Paid [Hiring] photo and video gigs from r/forhire via the arctic-shift mirror",
    category="lens",
    vertical="lens",
    enabled_by_default=False,
)
def search_reddit_forhire(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch [Hiring] photo/video gigs from r/forhire via arctic-shift.

    ``roles`` is ignored on purpose: gig posts are not career titles, and the
    [Hiring] + photo/video gate is the filter. The mirror returns the newest
    100 posts; exact ``date_posted`` on every row lets downstream handle
    freshness.
    """
    logger.info("Fetching [Hiring] photo/video gigs from r/forhire...")
    data = _get_json(
        _API_URL,
        params={
            "subreddit": "forhire",
            "limit": "100",
            "sort": "desc",
            "fields": _FIELDS,
        },
    )
    posts = data.get("data") if isinstance(data, dict) else None
    if not isinstance(posts, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for post in posts:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict) or not _is_hiring(post):
            continue
        row = _normalize_post(post)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("r/forhire: found %d [Hiring] photo/video gigs", len(results))
    return results
