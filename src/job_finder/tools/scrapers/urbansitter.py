"""UrbanSitter (lookafter kind): babysitting one-offs and recurring sits by city.

UrbanSitter's public per-city SEO pages are a Next.js app that server-renders
the 4 newest postings into a ``<script id="__NEXT_DATA__">`` blob
(live-verified 2026-07-10)::

    GET https://www.urbansitter.com/babysitting-jobs/il/chicago

``props.pageProps.jobs`` holds each posting: ``booking.rate`` is the family's
own posted hourly number and is often null (those rows carry NO pay fields),
``booking.start``/``booking.end`` are exact sit datetimes ("2026-07-11
13:00:00"), ``created`` is the posting timestamp, plus ``numberOfChildren``,
``kidsAges``, city/state/zip, the family's own description, and ``type``
(one_time or recurring). The job id maps to the public detail/apply page at
``https://www.urbansitter.com/job/{id}``.

Honesty notes: pay is emitted only when ``booking.rate`` is a number the
poster set. Titles are synthesized only from payload facts (kid count, ages,
recurring flag). Recurring sits stay on the board as lookafter, tagged via
``quest["schedule"]``, never hidden or dressed up as one-offs.

Politeness: robots.txt declares ``Crawl-delay: 3``, so the sweep sleeps at
least 3s between city pages and runs one polite sweep a day.

City coverage mirrors sittercity: ``_DEFAULT_CITY_PATHS`` seeds the big
metros and callers override with the ``city_paths`` kwarg (each entry is the
"st/city-slug" tail of the public URL). Each run costs one request per city
and reads the 4 newest postings there.
"""

from __future__ import annotations

import json
import logging
import re
import time

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.urbansitter.com"
_CITY_URL = _BASE + "/babysitting-jobs/{path}"
_JOB_URL = _BASE + "/job/{job_id}"

_DEFAULT_CITY_PATHS = (
    "il/chicago",
    "ny/new-york",
    "ca/los-angeles",
    "ca/san-francisco",
    "tx/austin",
    "ma/boston",
)

_CRAWL_DELAY_S = 3.0  # robots.txt: Crawl-delay: 3

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.DOTALL
)
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _extract_jobs(html: str) -> list[dict]:
    """Pull ``props.pageProps.jobs`` out of a city page, [] on anything bad."""
    if not html:
        return []
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("UrbanSitter __NEXT_DATA__ unparseable: %s", exc)
        return []
    if not isinstance(data, dict):
        return []
    jobs = data.get("props", {}).get("pageProps", {}).get("jobs")
    if not isinstance(jobs, list):
        return []
    return [j for j in jobs if isinstance(j, dict)]


def _fetch_city(path: str) -> list[dict]:
    url = _CITY_URL.format(path=path.strip("/"))
    try:
        # Ask for HTML explicitly: the shared headers' Accept is
        # application/json (the sittercity content-negotiation lesson).
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("UrbanSitter %s fetch failed: %s", path, exc)
        return []
    return _extract_jobs(resp.text)


def _iso_or_none(raw: object) -> str | None:
    """"2026-07-11 13:00:00" to "2026-07-11T13:00:00", None when unparseable."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw.strip()).isoformat()
    except ValueError:
        return None


def _synth_title(booking: dict, recurring: bool) -> str:
    """A title that only restates payload facts: kid count, ages, recurrence."""
    n = booking.get("numberOfChildren")
    ages = str(booking.get("kidsAges") or "").strip().strip("()").strip()
    if isinstance(n, int) and n > 0:
        title = f"Sitter for {n} {'child' if n == 1 else 'children'}"
    else:
        title = "Sitter needed"
    if ages:
        title += f" ({ages})"
    if recurring:
        title = "Recurring " + title[0].lower() + title[1:]
    return title


def _normalize_job(job: dict, city_label: str) -> dict | None:
    """One __NEXT_DATA__ job object to a lookafter-kind quest row, or None."""
    job_id = job.get("id")
    if not isinstance(job_id, int):
        return None
    booking = job.get("booking") if isinstance(job.get("booking"), dict) else {}
    jtype = str(job.get("type") or "").strip()
    recurring = jtype == "recurring"

    address = booking.get("address") if isinstance(booking.get("address"), dict) else {}
    city = str(address.get("city") or "").strip()
    state = str(address.get("state") or "").strip()
    location = f"{city}, {state}" if city and state else (city or city_label)

    parent = booking.get("parent") if isinstance(booking.get("parent"), dict) else {}
    first_name = str(parent.get("firstName") or "").strip()
    company = f"{first_name} via UrbanSitter" if first_name else "Posted via UrbanSitter"

    row: dict = {
        "title": _synth_title(booking, recurring),
        "company": company,
        "location": location,
        "url": _JOB_URL.format(job_id=job_id),
        "source": "urbansitter",
        "vertical": "lookafter",
        "description": str(booking.get("description") or "").strip(),
    }

    created = str(job.get("created") or "").strip()
    if _DATE_PREFIX_RE.match(created):
        row["date_posted"] = created[:10]

    start = _iso_or_none(booking.get("start"))
    if start:
        row["event_start"] = start
    end = _iso_or_none(booking.get("end"))
    if end:
        row["event_end"] = end

    # Pay only when the poster set a numeric hourly rate; null means no pay
    # fields at all, never a guess.
    rate = booking.get("rate")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        row.update(
            salary_min=float(rate),
            salary_max=float(rate),
            salary_period="hourly",
            salary_source="reported",
        )

    quest: dict = {}
    if jtype:
        quest["schedule"] = jtype
    ages = str(booking.get("kidsAges") or "").strip()
    if ages:
        quest["children"] = ages
    if quest:
        row["quest"] = quest
    return row


@register_scraper(
    name="urbansitter",
    display_name="UrbanSitter",
    url="https://www.urbansitter.com",
    description="Babysitting one-offs and recurring sits with the family's own posted hourly rate, by city",
    category="lookafter",
    kind="lookafter",
    # sits get filled fast; the city page only ever shows the 4 newest
    stale_after_days=7,
    # robots Crawl-delay 3; one polite sweep a day
    refresh_hours=24,
    allowed_url_hosts=("urbansitter.com",),
    enabled_by_default=False,
)
def search_urbansitter(
    roles: list[str] | None = None,
    max_results: int = 50,
    city_paths: list[str] | tuple[str, ...] | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch the newest sitting postings from UrbanSitter city pages.

    ``roles`` is ignored on purpose: sits are not career titles.
    ``city_paths`` overrides the default metro list ("st/city-slug").
    """
    paths = list(city_paths) if city_paths else list(_DEFAULT_CITY_PATHS)
    logger.info("Fetching sitting postings from UrbanSitter (%d cities)...", len(paths))

    results: list[dict] = []
    seen_urls: set[str] = set()
    for i, path in enumerate(paths):
        if len(results) >= max_results:
            break
        if i:
            time.sleep(_CRAWL_DELAY_S)
        city_label = path.split("/")[-1].replace("-", " ").title()
        for job in _fetch_city(path):
            if len(results) >= max_results:
                break
            row = _normalize_job(job, city_label)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)

    logger.info("UrbanSitter: %d postings", len(results))
    return results
