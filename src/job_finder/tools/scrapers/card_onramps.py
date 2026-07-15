"""Curated credit-card welcome-offer on-ramps (house kind).

These are standing quests, not scraped listings: each row is one well-known
card, the issuer's own offer page, and the welcome bonus exactly as the
issuer states it. The data below IS the content, so the search function
makes no network calls.

Reg Z compliance (strict): we NEVER quote an APR, an annual fee, or any rate
number ourselves. Each row renders only the welcome bonus and the spend
requirement in the issuer's words, and points at the issuer for every rate
and fee term ("terms on the issuer's site"). Only broadly available,
reputable cards belong here; no subprime or store cards.

Every bonus and URL was verified live on the issuer page on 2026-07-15:

- Chase Sapphire Preferred      https://creditcards.chase.com/rewards-credit-cards/sapphire/preferred
- Chase Freedom Unlimited       https://creditcards.chase.com/cash-back-credit-cards/freedom/unlimited
- Capital One Venture Rewards   https://www.capitalone.com/credit-cards/venture/
- Wells Fargo Active Cash       https://creditcards.wellsfargo.com/active-cash-credit-card
- Discover it Cash Back         https://www.discover.com/credit-cards/cash-back/it-card.html
- Bank of America Customized Cash Rewards  https://www.bankofamerica.com/credit-cards/products/cash-back-credit-card/

House rules for editing this list: never write a bonus or spend number the
issuer's page does not state, never quote a rate or fee, and re-verify every
row against the issuer page before changing it. Update the checked date in
``_LISTED`` and the header when you do. This lane carries affiliate links
later (the registry wires those); no affiliate code lives here.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_LISTED = "2026-07"

# spend == "" means the issuer states no minimum spend (Discover's match).
_CARDS: list[dict] = [
    {
        "card": "Chase Sapphire Preferred",
        "issuer": "Chase",
        "url": "https://creditcards.chase.com/rewards-credit-cards/sapphire/preferred",
        "bonus": "75,000 bonus points",
        "spend": "$5,000 on purchases in the first 3 months",
        "terms_site": "Chase's site",
    },
    {
        "card": "Chase Freedom Unlimited",
        "issuer": "Chase",
        "url": "https://creditcards.chase.com/cash-back-credit-cards/freedom/unlimited",
        "bonus": "a $200 bonus",
        "spend": "$500 on purchases in the first 3 months",
        "terms_site": "Chase's site",
    },
    {
        "card": "Capital One Venture Rewards",
        "issuer": "Capital One",
        "url": "https://www.capitalone.com/credit-cards/venture/",
        "bonus": "75,000 bonus miles",
        "spend": "$4,000 on purchases in the first 3 months",
        "terms_site": "Capital One's site",
    },
    {
        "card": "Wells Fargo Active Cash",
        "issuer": "Wells Fargo",
        "url": "https://creditcards.wellsfargo.com/active-cash-credit-card",
        "bonus": "a $200 cash rewards bonus",
        "spend": "$500 in purchases in the first 3 months",
        "terms_site": "Wells Fargo's site",
    },
    {
        "card": "Discover it Cash Back",
        "issuer": "Discover",
        "url": "https://www.discover.com/credit-cards/cash-back/it-card.html",
        # Discover's welcome offer is a match, not a fixed sum, and carries
        # no minimum spend; render exactly that.
        "bonus": "a dollar-for-dollar match of all the cash back you earn at the end of your first year",
        "spend": "",
        "terms_site": "Discover's site",
    },
    {
        "card": "Bank of America Customized Cash Rewards",
        "issuer": "Bank of America",
        "url": "https://www.bankofamerica.com/credit-cards/products/cash-back-credit-card/",
        "bonus": "a $200 online cash rewards bonus",
        "spend": "$1,000 in purchases in the first 90 days",
        "terms_site": "Bank of America's site",
    },
]


def _row(card: dict) -> dict:
    spend = card["spend"]
    if spend:
        lead = f"{card['bonus']} after you spend {spend}"
        catch = (
            "a hard credit pull; only worth it if you clear the spend "
            "without overspending and never carry a balance"
        )
    else:
        lead = f"{card['bonus']} (no minimum spend)"
        catch = (
            "a hard credit pull; only worth it if you would use the card "
            "anyway and never carry a balance"
        )
    description = f"{lead}, as listed {_LISTED}; terms on {card['terms_site']}."
    return {
        "title": f"Earn the {card['card']} bonus",
        "company": card["issuer"],
        # do-anywhere quests carry no location, like bankrewards nationwide
        "location": "",
        "url": card["url"],
        "source": "card_onramps",
        "vertical": "house",
        "description": description,
        # never invent pay: a card bonus is not a wage
        "salary_min": None,
        "salary_max": None,
        # standing quests: no dates, no invented freshness
        "date_posted": "",
        "is_rolling": True,
        # a hard pull and approval are a real gate, not a friction-free start
        "first_quest_ok": False,
        "quest": {
            "bring": "good credit and the spend you would make anyway",
            "catch": catch,
        },
    }


@register_scraper(
    name="card_onramps",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated credit-card welcome-offer on-ramps, bonus and spend only, rate and fee terms left to the issuer",
    category="house",
    kind="house",
    # the list above is the source's entire set, so absence proves removal
    full_snapshot=True,
    # content only changes when this file is edited; weekly sweep keeps the
    # freshness contract satisfied without hammering anything
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=(
        "chase.com",
        "capitalone.com",
        "wellsfargo.com",
        "discover.com",
        "bankofamerica.com",
    ),
)
def search_card_onramps(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated credit-card welcome-offer quests.

    ``roles`` is ignored on purpose: card offers are not career titles.
    """
    results = [_row(card) for card in _CARDS[: max(0, max_results)]]
    logger.info("card_onramps: %d curated card welcome offers", len(results))
    return results
