"""bankrewards.io (house kind): structured bank and brokerage bonuses.

A community tool (born on r/churning) with the cleanest fields of any bonus
source: one POST returns JSON offers with a numeric ``bonus_cash``, state
availability, and the requirement type::

    POST https://bankrewards.io/api/offers   {"limit": 100}

Live-verified quirks (2026-07-09):

- GET returns method-not-allowed; the API is POST-only.
- ``limit`` caps at 100 and paging params are ignored; the top 100 active
  offers are the whole feed, which is fine for a board.
- It is a solo-maintained tool and could vanish; Doctor of Credit is the
  canonical companion source, so losing this one degrades fields, not
  coverage. The health endpoint will say so if it dies.

Only cash bonuses are ingested (``bonus_cash`` > 0); points and stock
offers would need a valuation we refuse to invent. Titles are composed
from the source's own fields, and requirements go in the description in
the source's own terms.
"""

from __future__ import annotations

import logging

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_API_URL = "https://bankrewards.io/api/offers"
_OFFER_TYPES = {"bank", "business_bank", "brokerage"}

_REQUIREMENT_WORDS = {
    "direct_deposit": "direct deposit",
    "debit_transactions": "debit card transactions",
    "deposit": "a deposit",
    "balance": "a minimum balance",
}


def _fetch_offers() -> list[dict]:
    try:
        resp = requests.post(
            _API_URL,
            json={"limit": 100},
            headers={**_HEADERS, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("bankrewards.io fetch failed: %s", exc)
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        inner = data.get("offers") or data.get("data")
        return inner if isinstance(inner, list) else []
    return []


def _requirement_text(offer: dict) -> str:
    req_type = (offer.get("requirement_type") or "").strip()
    if not req_type:
        return ""
    words = _REQUIREMENT_WORDS.get(req_type, req_type.replace("_", " "))
    amount = offer.get("requirement_amount")
    if amount:
        return f"Requires {words} of ${amount:,.0f}."
    return f"Requires {words}."


def _normalize_offer(offer: dict) -> dict | None:
    """One API offer to a house-kind quest row, or None to skip."""
    if offer.get("offer_type") not in _OFFER_TYPES:
        return None
    bonus = offer.get("bonus_cash")
    if not isinstance(bonus, (int, float)) or bonus <= 0:
        return None
    name = (offer.get("name") or "").strip()
    link = (offer.get("offer_link") or "").strip()
    if not name or not link.startswith("http"):
        return None

    subtitle = (offer.get("name_subtitle") or "").strip()
    title = f"{name} ${bonus:,.0f} Bonus"
    if subtitle:
        title = f"{name} ${bonus:,.0f} {subtitle} Bonus"

    states = offer.get("location")
    location = ", ".join(states) if isinstance(states, list) and states else ""

    parts = [_requirement_text(offer)]
    fee = offer.get("termination_fee")
    if isinstance(fee, (int, float)) and fee > 0:
        parts.append(f"Early termination fee ${fee:,.0f}.")
    description = " ".join(p for p in parts if p)

    quest = {
        key: offer[field]
        for field, key in (
            ("requirement_type", "requirement_type"),
            ("requirement_amount", "requirement_amount"),
            ("expiration", "expires"),
        )
        if offer.get(field)
    }

    row: dict = {
        "title": title,
        "company": name,
        "location": location,
        "url": link,
        "source": "bankrewards",
        "vertical": "house",
        "description": description,
        "salary_min": float(bonus),
        "salary_max": float(bonus),
        "salary_source": "reported",
    }
    if quest:
        row["quest"] = quest
    if offer.get("created_at"):
        row["date_posted"] = str(offer["created_at"])
    return row


@register_scraper(
    name="bankrewards",
    display_name="BankRewards.io",
    url="https://bankrewards.io",
    description="Structured bank and brokerage cash bonuses with state availability and requirement type",
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
    """Fetch active cash bonuses from bankrewards.io.

    ``roles`` is ignored on purpose: bonuses are not career titles.
    """
    logger.info("Fetching cash bonuses from bankrewards.io...")
    offers = _fetch_offers()

    results: list[dict] = []
    seen_urls: set[str] = set()
    for offer in offers:
        if len(results) >= max_results:
            break
        if not isinstance(offer, dict):
            continue
        row = _normalize_offer(offer)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("bankrewards.io: %d cash bonuses", len(results))
    return results
