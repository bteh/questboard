"""Curated start-selling and start-renting on-ramps (flip kind).

These are standing quests, not scraped listings: each row is one platform,
one verb, the platform's own start page, and the seller fee exactly as the
platform's official fee page states it. The data below IS the content, so
the search function makes no network calls.

Every fee and URL was verified live on 2026-07-14 against the official page:

- eBay      https://www.ebay.com/help/selling/fees-credits-invoices/selling-fees?id=4822
- Poshmark  https://support.poshmark.com/s/article/297755057
- Mercari   https://www.mercari.com/us/help_center/article/169/
- Whatnot   https://help.whatnot.com/hc/en-us/articles/4847069165965-Whatnot-seller-fees
- Depop     https://depophelp.zendesk.com/hc/en-gb/articles/360001791127-Seller-fees-and-charges
- Vinted    https://www.vinted.com/help/373-is-selling-on-vinted-free
- Facebook  https://www.facebook.com/help/449101635835192
- Turo      https://help.turo.com/en_us/earnings-plans-in-detail-us-hosts-ByMOIVxEc

House rules for editing this list: never write a number the official page
does not state, never estimate earnings, and keep the no-fee platforms
(Facebook Marketplace local, Vinted) as full equals even though they can
never pay a referral. Re-verify every fee against the pages above before
changing a row, and update the checked date in the description.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_FEE_CHECKED = "2026-07-14"

_ONRAMPS: list[dict] = [
    {
        "title": "Sell almost anything on eBay",
        "company": "eBay",
        "bring": 'photos of what you\'re selling',
        "catch": "eBay takes 13.6% of the sale (13.25% on trading cards) plus $0.30 to $0.40 per order",
        "url": "https://www.ebay.com/sell",
        "description": (
            "List what you are not using and ship it when it sells. "
            "eBay takes a 13.6% final value fee on most categories and 13.25% "
            "on trading cards (each on the amount up to $7,500 per item, 2.35% "
            "above that), plus $0.30 per order at $10 or under and $0.40 over; "
            f"your first 250 listings each month are free (fee page checked {_FEE_CHECKED})."
        ),
        # free to list, nothing at risk until it sells
        "first_quest_ok": True,
    },
    {
        "title": "Sell the clothes you don't wear",
        "company": "Poshmark",
        "bring": 'photos of your clothes',
        "catch": "Poshmark takes $2.95 under $15, and 20% at $15 or more",
        "url": "https://poshmark.com/sell",
        "description": (
            "List clothes from your phone and ship when something sells. "
            "Poshmark takes $2.95 on sales under $15 and 20% on sales of $15 "
            f"or more (fee page checked {_FEE_CHECKED})."
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Sell your spare stuff on Mercari",
        "company": "Mercari",
        "bring": 'photos of what you\'re selling',
        "catch": "Mercari takes 10% of the item price and buyer-paid shipping",
        "url": "https://www.mercari.com/sell/",
        "description": (
            "List it free and ship when it sells. Mercari takes a 10% selling "
            "fee on the item price and buyer-paid shipping "
            f"(fee page checked {_FEE_CHECKED})."
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Sell it live on Whatnot",
        "company": "Whatnot",
        "bring": 'a seller application first',
        "catch": "seller approval required; Whatnot takes 8% plus 2.9% and $0.30 processing",
        "url": "https://www.whatnot.com/sell",
        "description": (
            "Apply for a seller account, then sell in live auctions. Whatnot "
            "takes an 8% commission on the final sale price plus a payment "
            "processing fee of 2.9% of the total order value and $0.30 per "
            f"transaction (fee page checked {_FEE_CHECKED})."
        ),
        # seller approval is a real gate, so not a friction-free first quest
        "first_quest_ok": False,
    },
    {
        "title": "Sell your vintage finds on Depop",
        "company": "Depop",
        "bring": 'photos of your clothes',
        "catch": "no Depop selling fee; card processing takes 3.3% plus $0.45",
        "url": "https://www.depop.com/sell/",
        "description": (
            "List your clothes and ship when they sell. Depop charges US "
            "sellers no selling fee, only a 3.3% + $0.45 payment processing "
            f"fee on each sale (fee page checked {_FEE_CHECKED})."
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Sell your clothes fee-free on Vinted",
        "company": "Vinted",
        "bring": 'photos of your clothes',
        "catch": "no seller fees; buyers pay Vinted's protection fee",
        "url": "https://www.vinted.com/items/new",
        "description": (
            "List your clothes and ship when they sell. Vinted charges "
            "sellers no fees, you receive the full selling price; buyers pay "
            f"a separate Buyer Protection fee (fee page checked {_FEE_CHECKED})."
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Sell it locally on Facebook Marketplace",
        "company": "Facebook Marketplace",
        "bring": 'photos and a public meetup spot',
        "catch": "free for local pickup; shipped checkout orders carry a 10% fee, $0.80 minimum",
        "url": "https://www.facebook.com/marketplace/",
        "description": (
            "List it and hand it off in person. Facebook Marketplace charges "
            "no selling fee on local pickup sales; orders shipped with "
            "checkout carry a 10% selling fee with a $0.80 minimum per order "
            f"(fee page checked {_FEE_CHECKED})."
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Rent out your car when you're not driving it",
        "company": "Turo",
        "bring": 'a car you own',
        "catch": "you keep 70%, 80%, or 90% of the trip price by plan; each plan carries a damage responsibility",
        "url": "https://turo.com/us/en/list-your-car",
        "description": (
            "List your car and set when it is available to rent. Turo hosts "
            "earn 70%, 80%, or 90% of the trip price depending on the "
            "earnings plan they choose; each plan carries a different damage "
            f"responsibility (fee page checked {_FEE_CHECKED})."
        ),
        # your car is on the line (per-claim damage responsibility)
        "first_quest_ok": False,
    },
]


@register_scraper(
    name="flip_onramps",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated start-selling and start-renting on-ramps",
    category="flip",
    kind="flip",
    # the list below is the source's entire set, so absence proves removal
    full_snapshot=True,
    # content only changes when this file is edited; weekly sweep keeps
    # the freshness contract satisfied without hammering anything
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=(
        "ebay.com",
        "poshmark.com",
        "mercari.com",
        "whatnot.com",
        "depop.com",
        "vinted.com",
        "facebook.com",
        "turo.com",
    ),
)
def search_flip_onramps(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated on-ramp quests.

    ``roles`` is ignored on purpose: on-ramps are not career titles.
    """
    results: list[dict] = []
    for entry in _ONRAMPS[: max(0, max_results)]:
        results.append(
            {
                "title": entry["title"],
                "company": entry["company"],
                # do-anywhere quests carry no location, like bankrewards
                "location": "",
                "url": entry["url"],
                "source": "flip_onramps",
                "vertical": "flip",
                "description": entry["description"],
                # never invent pay: no platform states an earning amount
                "salary_min": None,
                "salary_max": None,
                # standing quests: no dates, no invented freshness
                "date_posted": "",
                "is_rolling": True,
                "first_quest_ok": entry["first_quest_ok"],
                # source-stated card copy: the fee is the catch, the bring is
                # what starting genuinely takes; the poster prefers these over
                # the kind template
                "quest": {"bring": entry["bring"], "catch": entry["catch"]},
            }
        )
    logger.info("flip_onramps: %d curated on-ramps", len(results))
    return results
