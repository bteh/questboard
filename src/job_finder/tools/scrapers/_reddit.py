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
from datetime import datetime, timedelta, timezone

from job_finder.tools.scrapers._utils import _parse_posted_date

ARCTIC_API_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
ARCTIC_FIELDS = "author,created_utc,link_flair_text,selftext,title,url"
THREAD_PREFIX = "https://www.reddit.com/r/"

REMOVED_BODIES = frozenset({"[removed]", "[deleted]"})

# The one Reddit carve-out. The 2026-07-10 curation verdict made every
# subreddit research-only; on 2026-10-08 the owner (in Los Angeles)
# approved exactly these two as board content. Every subreddit scraper
# derives research_only from this set, so a sub not listed here can never
# publish. Lowercase names.
BOARD_SUBREDDITS = frozenset({"lajobs", "castingcalls"})


def research_only_for(subreddit: str) -> bool:
    return subreddit.lower() not in BOARD_SUBREDDITS


# Board subs have no mod flairs to gate on, so these are the house rules
# that apply to their rows: adult work, known scam shapes (car decals,
# account rentals), and pay-in-kind.
HOUSE_RULES_RE = re.compile(
    r"fetish|onlyfans|fansly|\bnsfw\b|\bnudes?\b|\bnudity\b|boudoir|lingerie"
    r"|sugar ?(?:daddy|baby)|content pics|big boob|large breast|no clothes"
    r"|foot (?:model|pic|jewelry)|feet pic|\bescort|\bdecal\b|car wrap|vehicle wrap"
    r"|account (?:task|rental)|linkedin account|gift ?cards?",
    re.IGNORECASE,
)

UNPAID_RE = re.compile(
    r"\bunpaid\b|\bnon[- ]?paid\b|\bno pay\b|\bnot paid\b|\bvolunteer|\bfree gig\b"
    r"|\btfp\b|no[- ]budget|\bfor credit\b|\bpassion project\b|\bfandub\b",
    re.IGNORECASE,
)

LA_LABEL = "Los Angeles, CA"

# Order matters only on a tie at the same text position: LA names win.
_PLACES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(
        r"\blos angeles\b|\bdtla\b|\bhollywood\b|\bburbank\b|\bsanta monica\b"
        r"|\blong beach\b|\bpasadena\b|\bglendale\b|\bsouth bay\b|\bwestside\b"
        r"|\bsylmar\b|\bparamount\b|\bcarson\b|\bculver city\b|\binglewood\b"
        r"|\btorrance\b|\bmanhattan beach\b|\bkoreatown\b|\bvan nuys\b"
        r"|\bsan fernando valley\b|\bmid[- ]wilshire\b|\bsilver lake\b|\becho park\b",
        re.IGNORECASE,
    ), LA_LABEL),
    (re.compile(r"\bLA\b|\bL\.A\."), LA_LABEL),
    (re.compile(r"\borange county\b|\birvine\b|\banaheim\b|\bbrea\b", re.IGNORECASE),
     "Orange County, CA"),
    (re.compile(r"\bcorona\b|\briverside\b|\binland empire\b", re.IGNORECASE),
     "Inland Empire, CA"),
    (re.compile(r"\bsan diego\b", re.IGNORECASE), "San Diego, CA"),
    (re.compile(r"\bfremont\b|\bbay area\b|\bsan francisco\b|\bsan jose\b", re.IGNORECASE),
     "Bay Area, CA"),
    (re.compile(r"\b(?:las )?vegas\b", re.IGNORECASE), "Las Vegas, NV"),
    (re.compile(r"\bnew york\b|\bnyc\b", re.IGNORECASE), "New York, NY"),
    (re.compile(r"\bhouston\b", re.IGNORECASE), "Houston, TX"),
    (re.compile(r"\bseattle\b", re.IGNORECASE), "Seattle, WA"),
    (re.compile(r"\bdenver\b", re.IGNORECASE), "Denver, CO"),
    (re.compile(r"\bchicago\b", re.IGNORECASE), "Chicago, IL"),
    (re.compile(r"\batlanta\b", re.IGNORECASE), "Atlanta, GA"),
    (re.compile(r"\bmiami\b", re.IGNORECASE), "Miami, FL"),
    (re.compile(r"\bcincinnati\b", re.IGNORECASE), "Cincinnati, OH"),
    (re.compile(r"\bistanbul\b", re.IGNORECASE), "Istanbul, Turkey"),
    (re.compile(r"\bremote\b", re.IGNORECASE), "Remote"),
)


def stated_place(*texts: str) -> str | None:
    """The first place a post names, checking ``texts`` in order (title
    before body), earliest mention within a text. None when none is named."""
    for text in texts:
        if not text:
            continue
        best: tuple[int, int, str] | None = None
        for rank, (pattern, label) in enumerate(_PLACES):
            m = pattern.search(text)
            if m and (best is None or (m.start(), rank) < best[:2]):
                best = (m.start(), rank, label)
        if best is not None:
            return best[2]
    return None


def is_removed(post: dict) -> bool:
    """Body snapshotted as removed or deleted: a mod or the author pulled it."""
    return (post.get("selftext") or "").strip() in REMOVED_BODIES

# One money mention: optional ~, $, amount (optional k), optional range tail,
# optional +, optional per-unit word ("/hr", "per video", "a video").
_PAY_RE = re.compile(
    r"~?\$\s*(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s*([kK])\b)?"
    r"(?:\s*(?:-|\u2013|to)\s*\$?\s*(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s*([kK])\b)?)?"
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


def older_than(post: dict, days: int) -> bool:
    """Posted more than ``days`` ago. Unknown dates are kept."""
    posted = _parse_posted_date(post.get("created_utc"))
    if posted is None:
        return False
    return posted < datetime.now(timezone.utc) - timedelta(days=days)
