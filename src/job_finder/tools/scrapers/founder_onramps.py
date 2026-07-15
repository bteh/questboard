"""Curated funding on-ramps for young builders and founders (pitch kind).

The pitch lane is refocused on funding for young builders, founders, and
students shipping startups and apps. There is no single feed for that, so
the honest supply is one poster per marquee program pointing at its real
application page, the same curated-data shape as the flip and study
on-ramps. The data below IS the content, so the search function makes no
network calls.

Every program, its application URL, and what it offers were verified live
on 2026-07-15. Amounts render only as the program's own site states them:

- Y Combinator       https://www.ycombinator.com/apply
                     ($500,000 per the deal page: ycombinator.com/deal)
- a16z Speedrun      https://a16z.com/speedrun/ ("up to $1M", SR007 cohort)
- Techstars          https://www.techstars.com/accelerators (three-month program)
- Antler             https://www.antler.co/apply (residency, no fixed first check stated)
- South Park Commons https://www.southparkcommons.com/founder-fellowship
                     ("Funding from $1M to $10M", F26 cohort open)
- Entrepreneur First https://apply.joinef.com ("up to $250K once you form a company")
- Z Fellows          https://www.zfellows.com/ ("1 week. $10,000.")
- Neo Scholars       https://neo.com/scholars (undergraduates in CS; no grant figure stated)
- Thiel Fellowship   https://thielfellowship.org/ ("$250,000" over "two years")
- 1517 Fund          https://www.1517fund.com/ (first checks $50k to $1M; Medici $1,000 grants)
- Emergent Ventures  https://www.mercatus.org/emergent-ventures (applicants 13+; no grant figure stated)

Verified dead or off-ICP on 2026-07-15; do not re-add without a live check:

- buildspace (buildspace.so): shut down, its page is a farewell note with
  no program to apply to.
- On Deck (beondeck.com): redirects to joinodf.com; the current ODF program
  is a non-dilutive one-week community with perks, not founder funding.
- Contrary Fellowship (contrary.com/fellowship): the URL serves the firm's
  home page, no live fellowship application page to point at.

Re-verify playbook, run before editing any row: open the row's URL and
confirm it still loads a real application page; confirm the program still
states the amount or cadence written here on its own site; write a dollar
figure ONLY if the program's own page states one; then update the checked
date below. Drop any program you cannot verify loads live.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_CHECKED = "2026-07-15"

_ONRAMPS: list[dict] = [
    {
        "title": "Apply to Y Combinator",
        "company": "Y Combinator",
        "url": "https://www.ycombinator.com/apply",
        "description": (
            "Apply to Y Combinator and go through a funded batch with a "
            "partner and a founder community. YC states it invests $500,000 "
            "in every company it funds, $125,000 for 7% on a post-money safe "
            "plus $375,000 on an uncapped safe with an MFN provision, and "
            f"runs batches through the year (checked {_CHECKED})."
        ),
        "bring": "an idea or early product and a founding team (solo founders can apply)",
        "catch": (
            "very competitive, and the two safes mean YC takes equity; batches "
            "run on set deadlines, so check their site for the next one"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to a16z Speedrun",
        "company": "a16z Speedrun",
        "url": "https://a16z.com/speedrun/",
        "description": (
            "Apply to a16z Speedrun, the games and AI accelerator run by "
            "Andreessen Horowitz. Its page states it invests up to $1M in "
            "your startup and runs in cohorts (SR007 in San Francisco), so "
            f"the dates move each round (checked {_CHECKED})."
        ),
        "bring": "an early game, app, or AI product and a short application",
        "catch": (
            "very competitive and cohort-based on set dates; Speedrun takes "
            "equity for its investment"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to a Techstars accelerator",
        "company": "Techstars",
        "url": "https://www.techstars.com/accelerators",
        "description": (
            "Apply to a Techstars accelerator, a mentor-driven program that "
            "runs in cities worldwide. Techstars states it is a three-month "
            "program and invests in the companies it accepts; check the "
            f"specific accelerator page for its terms (checked {_CHECKED})."
        ),
        "bring": "an early startup and a completed accelerator application",
        "catch": (
            "very competitive; each accelerator runs a fixed three-month cohort "
            "by city and takes equity for its investment"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to Antler",
        "company": "Antler",
        "url": "https://www.antler.co/apply",
        "description": (
            "Apply to Antler, a residency that backs founders from day zero at "
            "one of its global locations. Antler states it provides capital, "
            "network, and conviction and lists cohort start dates through "
            "2026; it does not publish a single fixed first-check figure, so "
            f"check your location's page (checked {_CHECKED})."
        ),
        "bring": "a willingness to build full-time, with or without a co-founder yet",
        "catch": (
            "very competitive; Antler is a full-time residency at one of its "
            "locations and invests for equity"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to the South Park Commons Founder Fellowship",
        "company": "South Park Commons",
        "url": "https://www.southparkcommons.com/founder-fellowship",
        "description": (
            "Apply to the South Park Commons Founder Fellowship, a six-month "
            "ideation residency for people who want to start a company. SPC "
            "states the fellowship has no cost or equity, and lists funding "
            "from $1M to $10M for founders building a venture-scale company, "
            f"with the F26 cohort open (checked {_CHECKED})."
        ),
        "bring": "a track record of building and conviction you want to start a company",
        "catch": (
            "very competitive; the fellowship is a six-month residency and the "
            "F26 cohort has a set application window"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to Entrepreneur First",
        "company": "Entrepreneur First",
        "url": "https://apply.joinef.com",
        "description": (
            "Apply to Entrepreneur First, which backs individuals before they "
            "have a company or a co-founder and runs cohorts at its global "
            "offices. EF states an equity-free grant during the ideation phase "
            f"and up to $250K of investment once you form a company (checked {_CHECKED})."
        ),
        "bring": "a willingness to build full-time; you can apply before you have a company",
        "catch": (
            "very competitive; EF is a full-time cohort at one of its offices, "
            "and its investment is for equity once you form a company"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to Z Fellows",
        "company": "Z Fellows",
        "url": "https://www.zfellows.com/",
        "description": (
            "Apply to Z Fellows, a one-week program that brings ten builders "
            "together with founders of large companies. Its page states "
            "'1 week. $10,000,' where the $10,000 is an optional investment at "
            f"a $1 billion valuation cap (checked {_CHECKED})."
        ),
        "bring": "something you have built and a short application",
        "catch": (
            "very competitive; it runs in weekly cohorts and the $10,000 is an "
            "optional investment at a $1 billion cap"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to Neo Scholars",
        "company": "Neo Scholars",
        "url": "https://neo.com/scholars",
        "description": (
            "Apply to Neo Scholars, a selective program whose page invites "
            "undergraduates who excel at computer science. Neo states it is "
            "for standout CS undergraduates; its page does not publish a fixed "
            f"grant figure, so check it for current terms (checked {_CHECKED})."
        ),
        "bring": "current undergraduate enrollment and strong computer-science work",
        "catch": "undergraduates only, and it is highly selective",
        "first_quest_ok": True,
    },
    {
        "title": "Join the Thiel Fellowship",
        "company": "Thiel Fellowship",
        "url": "https://thielfellowship.org/",
        "description": (
            "Join the Thiel Fellowship, which backs young people who want to "
            "build instead of staying in school. Its page states a grant of "
            "$250,000 over two years and that fellows skip or stop out of "
            f"college to take it (checked {_CHECKED})."
        ),
        "bring": "a project you would leave school to build and an application",
        "catch": (
            "you must be young and willing to skip or stop out of college to "
            "take the grant, and it is extremely competitive"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Write in to the 1517 Fund",
        "company": "1517 Fund",
        "url": "https://www.1517fund.com/",
        "description": (
            "Write in to the 1517 Fund, which backs dropouts and renegade "
            "students working on hard problems. 1517 states first checks from "
            "$50,000 to $1,000,000 for startups, and a Medici program that "
            "gives minimum $1,000 grants to validate an idea before you have a "
            f"company (checked {_CHECKED})."
        ),
        "bring": "an early idea or research and a short write-in; you do not need a company yet",
        "catch": (
            "very competitive; the fund backs on a rolling write-in basis and "
            "its first checks are for in-thesis founders (dropouts, students, "
            "deep-tech scientists)"
        ),
        "first_quest_ok": True,
    },
    {
        "title": "Apply to Emergent Ventures",
        "company": "Emergent Ventures",
        "url": "https://www.mercatus.org/emergent-ventures",
        "description": (
            "Apply to Emergent Ventures, a grants and fellowship program from "
            "the Mercatus Center for ambitious zero-to-one ideas. Its page "
            "states grants for entrepreneurs and brilliant minds, that "
            "applicants must be 13 or older, and it takes a rolling online "
            f"application; it does not publish a fixed grant figure (checked {_CHECKED})."
        ),
        "bring": "a specific zero-to-one project and an online application",
        "catch": (
            "very competitive and open-ended; you write in with a project and "
            "wait to hear back"
        ),
        "first_quest_ok": True,
    },
]


@register_scraper(
    name="founder_onramps",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated funding on-ramps for young builders, founders, and students",
    category="pitch",
    kind="pitch",
    # the list below is the source's entire set, so absence proves removal
    full_snapshot=True,
    # content only changes when this file is edited; weekly sweep keeps
    # the freshness contract satisfied without hammering anything
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=(
        "ycombinator.com",
        "a16z.com",
        "techstars.com",
        "antler.co",
        "southparkcommons.com",
        "joinef.com",
        "zfellows.com",
        "neo.com",
        "thielfellowship.org",
        "1517fund.com",
        "mercatus.org",
    ),
)
def search_founder_onramps(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated founder-funding on-ramp quests.

    ``roles`` is ignored on purpose: on-ramps are not career titles.
    """
    results: list[dict] = []
    for entry in _ONRAMPS[: max(0, max_results)]:
        results.append(
            {
                "title": entry["title"],
                "company": entry["company"],
                # apply-from-anywhere programs carry no location, like flip
                "location": "",
                "url": entry["url"],
                "source": "founder_onramps",
                "vertical": "pitch",
                "description": entry["description"],
                # never invent pay: a grant or investment is not a salary, and
                # amounts live in the description exactly as each site states
                "salary_min": None,
                "salary_max": None,
                # standing quests: no dates, no invented freshness
                "date_posted": "",
                "is_rolling": True,
                "first_quest_ok": entry["first_quest_ok"],
                # source-stated card copy: the catch is the real gate
                # (competitive, batch deadlines, equity), the bring is what
                # applying genuinely takes
                "quest": {"bring": entry["bring"], "catch": entry["catch"]},
            }
        )
    logger.info("founder_onramps: %d curated on-ramps", len(results))
    return results
