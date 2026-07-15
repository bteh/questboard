"""Curated LA focus-group facility on-ramps (study kind).

No LA facility publishes a public per-study board: they are all
register-first, and studies arrive by email after you join their panel
(checked facility by facility on 2026-07-14). So the honest LA supply for
the think lane is one poster per facility pointing at its participant
registration page, the same curated-data shape as the flip on-ramps. The
data below IS the content, so the search function makes no network calls.

Every facility, URL, city, and process claim was verified live on 2026-07-14:

- Adler Weiner     https://adlerweiner.com/participate-in-la-oc
                   (pay process: https://adlerweiner.com/frequently-asked-questions)
- Fieldwork        https://www.fieldwork.com/join/
                   (Irvine venue: https://www.fieldwork.com/us-research-venues/la-orange-county/)
- Sago             https://www.focusgroup.com/
                   (Culver City venue: https://sago.com/en/locations/los-angeles/)
- Focus & Testing  https://focusandtesting.com/participate/
                   (Calabasas address: https://focusandtesting.com/contact-us/;
                   sign-up portal: https://research.focusandtesting.com/ARCSPages/signin.asp)
- watchLAB         https://watchlab.com/sign-up/
                   (the form lists the Los Angeles metro; watchlab.com names no LA facility)

Verified dead or unusable on 2026-07-14; do not re-add without a live check:

- Curion: its register page (curionpanelist.com/register) lists seven
  facility locations and none is in the LA area.
- House of Marketing Research (Pasadena): real facility, but its site has
  no public participant sign-up page (sitemap is home + blog only).
- Advanced Marketing Perspectives (Sherman Oaks): its site, ampincww.com,
  no longer resolves.
- Meczka and Plaza Research: dead facilities.

Re-verify playbook, run before editing any row: open the row's URL and
confirm it still loads a real sign-up page; confirm the facility still
states its LA-area city on its own site; write a dollar figure ONLY if
the facility's own page states one (none did on the last check, so rows
carry no figures); then update the checked date below.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_CHECKED = "2026-07-14"

_ONRAMPS: list[dict] = [
    {
        "title": "Join Adler Weiner's paid focus group panel",
        "company": "Adler Weiner Research",
        "location": "Los Angeles",
        "url": "https://adlerweiner.com/participate-in-la-oc",
        "description": (
            "Sign up for Adler Weiner's Los Angeles and Orange County "
            "database to get picked for in-person focus groups, interviews, "
            "and in-home studies. Their FAQ states each project has a "
            "predetermined honorarium (cash, check, gift card, prepaid debit "
            "card, or product) and that you are told the type and amount "
            f"before you commit (checked {_CHECKED})."
        ),
        "bring": "a few minutes to fill their sign-up survey",
        "catch": (
            "studies come by email or phone after you register; an email "
            "screener and a recruiter call decide who gets picked"
        ),
    },
    {
        "title": "Join Fieldwork's paid research panel",
        "company": "Fieldwork LA - Orange County",
        "location": "Irvine",
        "url": "https://www.fieldwork.com/join/",
        "description": (
            "Create a profile with Fieldwork to get invited to focus groups "
            "and interviews at its Irvine office or online. Their join page "
            "states you receive an incentive for participating, typically "
            f"sent within 2 weeks (checked {_CHECKED})."
        ),
        "bring": "a few minutes to build your participant profile",
        "catch": (
            "invitations arrive by email or phone when a study matches your "
            "profile; their screener questions decide who gets picked"
        ),
    },
    {
        "title": "Join Sago's paid focus group panel",
        "company": "Sago",
        "location": "Culver City",
        "url": "https://www.focusgroup.com/",
        "description": (
            "Register on Focus Group, Sago's participant panel, to get "
            "invited to studies at its Culver City facility and online. Sago "
            "states the process as register, verify your identity, then "
            "receive invitations for studies that match your profile "
            f"(checked {_CHECKED})."
        ),
        "bring": "a few minutes to register and verify your identity",
        "catch": (
            "studies come by email after you register; a screener decides "
            "who gets picked, and Sago requires identity verification first"
        ),
    },
    {
        "title": "Join Focus & Testing's paid taste test panel",
        "company": "Focus & Testing",
        "location": "Calabasas",
        "url": "https://focusandtesting.com/participate/",
        "description": (
            "Sign up as a research participant and taste tester with Focus & "
            "Testing, a Calabasas taste test center that also runs focus "
            "groups. Their participate page states no sales, no cost to you, "
            "and that your contact information is never sold "
            f"(checked {_CHECKED})."
        ),
        "bring": "a few minutes to register in their respondent portal",
        "catch": (
            "studies come by email after you register and a screener decides "
            "who gets picked; choose the Los Angeles option when signing up"
        ),
    },
    {
        "title": "Join watchLAB's paid research panel",
        "company": "watchLAB",
        "location": "Los Angeles",
        "url": "https://watchlab.com/sign-up/",
        "description": (
            "Register with watchLAB, a market research recruiter whose "
            "sign-up form covers the Los Angeles metro, for focus groups, "
            "interviews, and user tests. The form asks for demographics and "
            "consent to email and text invitations; their site states no pay "
            f"amounts up front (checked {_CHECKED})."
        ),
        "bring": "a few minutes to fill their sign-up form",
        "catch": (
            "studies come by email or text after you register; a screener "
            "decides who gets picked"
        ),
    },
]


@register_scraper(
    name="study_onramps",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated join-the-panel on-ramps for LA focus group facilities",
    category="study",
    kind="study",
    # the list below is the source's entire set, so absence proves removal
    full_snapshot=True,
    # content only changes when this file is edited; weekly sweep keeps
    # the freshness contract satisfied without hammering anything
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=(
        "adlerweiner.com",
        "fieldwork.com",
        "focusgroup.com",
        "focusandtesting.com",
        "watchlab.com",
    ),
)
def search_study_onramps(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated facility on-ramp quests.

    ``roles`` is ignored on purpose: on-ramps are not career titles.
    """
    results: list[dict] = []
    for entry in _ONRAMPS[: max(0, max_results)]:
        results.append(
            {
                "title": entry["title"],
                "company": entry["company"],
                "location": entry["location"],
                "url": entry["url"],
                "source": "study_onramps",
                "vertical": "study",
                "description": entry["description"],
                # never invent pay: panel membership states no fixed amount
                "salary_min": None,
                "salary_max": None,
                # standing quests: no dates, no invented freshness
                "date_posted": "",
                "is_rolling": True,
                # joining a panel needs no prior experience anywhere
                "first_quest_ok": True,
                # source-stated card copy: the register-then-wait truth is
                # the catch, the bring is what signing up genuinely takes
                "quest": {"bring": entry["bring"], "catch": entry["catch"]},
            }
        )
    logger.info("study_onramps: %d curated on-ramps", len(results))
    return results
