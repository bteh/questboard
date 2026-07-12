"""CallingAllPapers (speak kind): open conference CFPs, one aggregated feed.

callingallpapers.com (a joind.in project) aggregates calls for papers
from Sessionize, PaperCall, confs.tech, and one-off conference sites.
One GET returns the entire open set (live-verified 2026-07-12, ~295
rows), so full_snapshot applies::

    GET https://api.callingallpapers.com/v1/cfp
    Accept: application/json          -> {"cfps": [...], "meta": {"count": N}}

No pagination. ``uri`` is the actual submission link and becomes the
row url; ``name`` is the event and stands in as counterparty context.
``dateCfpEnd`` becomes the quest's apply_by, and rows whose deadline
has already passed are dropped (a deadline can lapse between the
aggregator's crawl and ours). ``dateEventStart``/``dateEventEnd`` map
to the event window. A missing ``location`` means an online event.

On robots: api.callingallpapers.com/robots.txt says ``Disallow: /``,
but the project's own homepage links the API publicly, the project is
open source under the joind.in org, and the API docs invite clients.
Read together, that robots line de-indexes API URLs from search
engines; it is not an access restriction on API consumers. One polite
fetch a day is well inside the project's intent.

Speaking slots are not paid gigs ("exposure" is not pay) and the API
states no compensation, so rows never carry salary keys. ``uri`` spans
many legitimate hosts by design, so no allowed_url_hosts gate
(bankrewards precedent: the source points outward at other domains);
instead the scraper itself requires https and rejects link shorteners,
which hide the real destination.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_API_URL = "https://api.callingallpapers.com/v1/cfp"

_SHORTENER_DOMAINS = {
    "tinyurl.com", "bit.ly", "t.co", "goo.gl", "ow.ly", "buff.ly",
    "is.gd", "rb.gy", "tiny.cc", "cutt.ly", "shorturl.at", "rebrand.ly",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_cfps() -> list[dict]:
    try:
        resp = requests.get(_API_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("callingallpapers fetch failed: %s", exc)
        return []
    if isinstance(data, dict):
        inner = data.get("cfps")
        return inner if isinstance(inner, list) else []
    return []


def _acceptable_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    # papercall.io supply belongs to the papercall scraper: it lists the
    # same CFPs under different URLs (slug pages vs deep submission
    # links), so URL dedupe cannot catch the overlap; a clean partition
    # can. CAP keeps sessionize and one-off hosts.
    if host == "papercall.io" or host.endswith(".papercall.io"):
        return False
    # predatory pay-to-present conference mills are never a real stage
    # (audit 2026-07-12: a Paris "summit" on averconferences reached here)
    from job_finder.tools.scrapers._speak import is_predatory_host

    if is_predatory_host(uri):
        return False
    return not any(
        host == d or host.endswith("." + d) for d in _SHORTENER_DOMAINS
    )


def _parse_iso(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _normalize_cfp(cfp: dict, now: datetime) -> dict | None:
    """One API cfp to a speak-kind quest row, or None to skip."""
    name = str(cfp.get("name") or "").strip()
    uri = str(cfp.get("uri") or "").strip()
    if not name or not _acceptable_uri(uri):
        return None

    deadline = _parse_iso(cfp.get("dateCfpEnd"))
    if deadline is not None and deadline < now:
        return None
    if deadline is not None:
        from job_finder.tools.scrapers._speak import is_sentinel_deadline

        if is_sentinel_deadline(deadline):
            return None  # a placeholder far-future date is not a real deadline

    location = str(cfp.get("location") or "").strip()
    is_remote = not location

    parts: list[str] = []
    if deadline is not None:
        parts.append(f"CFP closes {deadline.date().isoformat()}.")
    start = _parse_iso(cfp.get("dateEventStart"))
    end = _parse_iso(cfp.get("dateEventEnd"))
    if start and end and end.date() > start.date():
        parts.append(f"Event {start.date().isoformat()} to {end.date().isoformat()}.")
    elif start:
        parts.append(f"Event on {start.date().isoformat()}.")
    tags = [str(t).strip() for t in (cfp.get("tags") or []) if str(t).strip()]
    if tags:
        parts.append(f"Topics: {', '.join(tags)}.")

    row: dict = {
        "title": f"Speak at {name}",
        "company": name,
        "location": location or "Online",
        "is_remote": is_remote,
        "url": uri,
        "source": "callingallpapers",
        "vertical": "speak",
        "description": " ".join(parts),
    }
    if deadline is not None:
        row["quest"] = {"apply_by": deadline.isoformat()}
    if cfp.get("dateEventStart"):
        row["event_start"] = str(cfp["dateEventStart"])
    if cfp.get("dateEventEnd"):
        row["event_end"] = str(cfp["dateEventEnd"])
    if cfp.get("lastChange"):
        row["date_posted"] = str(cfp["lastChange"])
    return row


@register_scraper(
    name="callingallpapers",
    display_name="CallingAllPapers",
    url="https://callingallpapers.com",
    description="Open conference CFPs aggregated from Sessionize, PaperCall, and conference sites",
    category="speak",
    kind="speak",
    # one GET is the entire open set, so absence proves a CFP closed
    full_snapshot=True,
    # the aggregator itself crawls daily; match that rhythm
    refresh_hours=24,
    enabled_by_default=False,
    # uris span many legit hosts (sessionize, papercall, one-off conference
    # domains) by design — see the module docstring for the https/shortener
    # gate the scraper applies itself
    allowed_url_hosts=None,
)
def search_callingallpapers(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch open CFPs from callingallpapers.com.

    ``roles`` is ignored on purpose: CFPs are not career titles.
    """
    logger.info("Fetching open CFPs from callingallpapers.com...")
    cfps = _fetch_cfps()
    now = _utcnow()

    results: list[dict] = []
    seen_urls: set[str] = set()
    for cfp in cfps:
        if len(results) >= max_results:
            break
        if not isinstance(cfp, dict):
            continue
        row = _normalize_cfp(cfp, now)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("callingallpapers: %d open CFPs", len(results))
    return results
