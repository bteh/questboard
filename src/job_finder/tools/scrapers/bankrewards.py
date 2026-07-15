"""bankrewards.io (house kind): structured personal and business bank bonuses.

A community tool (born on r/churning) with the cleanest fields of any bonus
source: one POST returns JSON offers with a numeric ``bonus_cash``, a state
array, and the requirement type::

    POST https://bankrewards.io/api/offers   {"limit": 100}

Live-verified quirks (2026-07-15, plain Mozilla/5.0 UA, HTTP 200):

- GET returns method-not-allowed; the API is POST-only. A normal browser UA
  clears Cloudflare with no JS challenge.
- ``limit`` caps near 100 (the D1 backend errors on too many SQL variables
  past ~150); the top-scored 100 offers are the whole board feed.
- ``location`` is ``["nationwide"]``, one state (``["MI"]``), or a state
  array. The full 461-offer catalog is also enumerable via the sitemap at
  https://www.bankrewards.io/sitemaps/offers.xml, but the POST feed is what
  the board ingests.
- ``offer_link`` is the real apply URL, but some rows carry bankrewards' own
  referral or affiliate-network redirect (bilt.page/r/, *.sjv.io,
  *.fintelconnect.com). Those are stripped (see below).

This lane keeps only bank and business_bank offers. Credit cards go to
card_onramps (Reg Z: we never quote a card's APR or fee), and brokerage
offers need a valuation we refuse to invent. Filters run in this order,
which is what kills the weak-lane junk (expired, tiny-geo, sub-$150):

  (a) offer_type in {bank, business_bank}
  (b) geo: nationwide, or available in at least three states
  (c) bonus_cash >= 150
  (d) recency: updated_at within ~90 days (presume older is dead)
  (e) referral strip: drop rows whose offer_link carries someone's
      referral/affiliate code (the feed exposes only offer_link, so there
      is no issuer-direct fallback to swap in)

Pay and terms render only as the source states them: the bonus is the stated
``bonus_cash``, the requirement is the source's own ``requirement_type`` and
``requirement_amount`` in plain words, and the geo is the stated state list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_API_URL = "https://bankrewards.io/api/offers"
_FETCH_LIMIT = 100

# This lane's default set. Cards -> card_onramps, brokerage needs a valuation.
_LANE_OFFER_TYPES = {"bank", "business_bank"}
_MIN_BONUS_CASH = 150
_RECENCY_DAYS = 90

# requirement_type -> (plain phrase, amount_is_a_dollar_figure). transactions
# amounts are sometimes a count and sometimes dollars in the feed, so we never
# attach a number to them.
_REQUIREMENT_PHRASES: dict[str, tuple[str, bool]] = {
    "direct_deposit": ("a direct deposit", True),
    "transfer": ("a transfer", True),
    "deposit": ("a deposit", True),
    "balance": ("a minimum balance", True),
    "spend": ("spending", True),
    "transactions": ("debit card transactions", False),
    "debit_transactions": ("debit card transactions", False),
}

# Hosts that redirect through an affiliate/referral network carrying
# bankrewards' own tracking code; feeding these hands our traffic to a
# competitor. bilt.page/r/ is the task-named example, sjv.io = Sovrn/Impact,
# fintelconnect = an affiliate network, and any bankrewards.io host is a
# self-redirect.
_REFERRAL_HOSTS = ("bilt.page", "sjv.io", "fintelconnect.com", "bankrewards.io")


def _now() -> datetime:
    """Naive UTC now; a seam tests patch for a stable recency window."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_offers() -> list[dict]:
    try:
        resp = requests.post(
            _API_URL,
            json={"limit": _FETCH_LIMIT},
            headers={**_HEADERS, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("bankrewards.io fetch failed: %s", exc)
        return []
    if isinstance(data, dict):
        inner = data.get("data") or data.get("offers")
        return inner if isinstance(inner, list) else []
    return data if isinstance(data, list) else []


def _parse_updated(value: object) -> datetime | None:
    """Parse an ISO timestamp (``...Z`` or ``+00:00``) to naive UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _is_referral_link(url: str) -> bool:
    """True when offer_link carries someone's referral or affiliate code."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    if any(host == h or host.endswith("." + h) for h in _REFERRAL_HOSTS):
        return True
    path = parsed.path.lower()
    if "/r/" in path or "referral" in path:
        return True
    return "ref" in parse_qs(parsed.query)


def _passes_geo(location: object) -> bool:
    if not isinstance(location, list) or not location:
        return False
    if len(location) == 1 and str(location[0]).lower() == "nationwide":
        return True
    return len(location) >= 3


def _requirement_text(offer: dict) -> str:
    phrase_pair = _REQUIREMENT_PHRASES.get((offer.get("requirement_type") or "").strip())
    if not phrase_pair:
        return ""
    phrase, amount_is_dollars = phrase_pair
    amount = offer.get("requirement_amount")
    if amount_is_dollars and isinstance(amount, (int, float)) and amount > 0:
        return f"{phrase} of ${amount:,.0f}"
    return phrase


def _normalize_offer(offer: dict, cutoff: datetime) -> dict | None:
    """One API offer to a house-kind quest row, or None to skip.

    Filters in the order (a)-(e) documented at the top of the module.
    """
    if offer.get("offer_type") not in _LANE_OFFER_TYPES:
        return None
    location = offer.get("location")
    if not _passes_geo(location):
        return None
    bonus = offer.get("bonus_cash")
    if not isinstance(bonus, (int, float)) or bonus < _MIN_BONUS_CASH:
        return None
    updated = _parse_updated(offer.get("updated_at"))
    if updated is None or updated < cutoff:
        return None
    link = (offer.get("offer_link") or "").strip()
    if not link.startswith("http") or _is_referral_link(link):
        return None
    name = (offer.get("name") or "").strip()
    if not name:
        return None

    states = [str(s) for s in location]
    nationwide = len(states) == 1 and states[0].lower() == "nationwide"
    location_field = "" if nationwide else ", ".join(states)
    geo_phrase = "nationwide" if nationwide else f"{', '.join(states)} only"

    requirement = _requirement_text(offer)
    listed = f"{updated.year:04d}-{updated.month:02d}"

    # "$550 after a direct deposit of $500, nationwide, as listed 2026-06"
    lead = f"${bonus:,.0f} after {requirement}" if requirement else f"${bonus:,.0f}"
    description = ", ".join([lead, geo_phrase, f"as listed {listed}"])
    catch = "; ".join(b for b in (requirement, geo_phrase) if b)

    row: dict = {
        "title": f"{name} ${bonus:,.0f} bonus",
        "company": name,
        "location": location_field,
        "url": link,
        "source": "bankrewards",
        "vertical": "house",
        "description": description,
        "salary_min": float(bonus),
        "salary_max": float(bonus),
        "salary_source": "reported",
        "date_posted": updated.date().isoformat(),
    }
    if catch:
        row["quest"] = {"catch": catch}
    return row


@register_scraper(
    name="bankrewards",
    display_name="BankRewards.io",
    url="https://bankrewards.io",
    description="Structured nationwide and multi-state bank cash bonuses with the requirement in the source's own terms",
    category="house",
    kind="house",
    # one POST returns the entire active set, so absence proves removal
    full_snapshot=True,
    # bonus set shifts daily at most
    refresh_hours=24,
    enabled_by_default=False,
)
def search_bankrewards(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch nationwide and multi-state bank cash bonuses from bankrewards.io.

    ``roles`` is ignored on purpose: bonuses are not career titles.
    """
    logger.info("Fetching bank cash bonuses from bankrewards.io...")
    offers = _fetch_offers()
    cutoff = _now() - timedelta(days=_RECENCY_DAYS)

    results: list[dict] = []
    seen_urls: set[str] = set()
    for offer in offers:
        if len(results) >= max_results:
            break
        if not isinstance(offer, dict):
            continue
        row = _normalize_offer(offer, cutoff)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("bankrewards.io: %d bank cash bonuses", len(results))
    return results
