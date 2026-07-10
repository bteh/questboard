"""Shared helpers for subreddit-backed quest sources (arctic-shift mirror).

Reddit blocks direct scraping from most IPs, so subreddit sources read the
sanctioned arctic-shift mirror, which archives posts within seconds::

    GET https://arctic-shift.photon-reddit.com/api/posts/search
        ?subreddit=<sub>&limit=100&sort=desc&fields=<FIELDS>

Each source stays one decorated file (the registry contract); what lives
here is everything they would otherwise copy-paste: the API constants, the
honest stated-pay extractor, and the removed-body hygiene. Keep scrapers'
own ``_get_json`` calls in their own modules so tests can patch them there.

Live-verified API quirks (see reddit_forhire.py for the originals):
- ``fields`` rejects ``permalink``; ``url`` carries the thread link for
  self posts.
- Automod-removed posts snapshot as "[removed]"; title, flair, date, and
  link are still real, but the placeholder must never leak into a
  description.
"""

from __future__ import annotations

import re

ARCTIC_API_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
ARCTIC_FIELDS = "author,created_utc,link_flair_text,selftext,title,url"
THREAD_PREFIX = "https://www.reddit.com/r/"

REMOVED_BODIES = frozenset({"[removed]", "[deleted]"})

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


def extract_pay(*texts: str) -> tuple[str | None, dict]:
    """First stated pay figure across ``texts`` -> (pay_note, salary fields).

    ``pay_note`` is the matched text verbatim. Salary keys are returned only
    for unambiguous statements: a time-rated figure or a plain range. A bare
    figure ("budget is $5000") or a per-piece rate ("$200/video") stays
    note-only, because a structured number would mislead.
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


def clean_body(post: dict) -> str:
    """The post body, or empty when automod snapshotted a placeholder."""
    body = (post.get("selftext") or "").strip()
    return "" if body in REMOVED_BODIES else body


def author_handle(post: dict, fallback: str) -> str:
    """u/<author> when real, else the given fallback (e.g. 'r/slavelabour')."""
    author = (post.get("author") or "").strip()
    return f"u/{author}" if author and author != "[deleted]" else fallback


def arctic_params(subreddit: str, limit: int = 100) -> dict[str, str]:
    """Query params for the newest posts of one subreddit."""
    return {
        "subreddit": subreddit,
        "limit": str(limit),
        "sort": "desc",
        "fields": ARCTIC_FIELDS,
    }
