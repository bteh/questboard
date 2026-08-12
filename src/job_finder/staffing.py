"""One staffing/recruiting-company rule for pull, board, and ranking.

The setting is a hard preference. Keeping the agency vocabulary in the
pipeline alone meant old rows and aggregator rows could still re-enter the
personalized board and assistant shortlist after the pull had excluded them.
"""

from __future__ import annotations


STAFFING_AGENCY_NAMES: frozenset[str] = frozenset({
    "adecco",
    "aerotek",
    "american it staff",
    "apex systems",
    "aston carter",
    "beacon hill staffing",
    "cybercoders",
    "dice staffing",
    "eleven recruiting",
    "express employment",
    "forward progress staffing",
    "hays",
    "insight global",
    "jobgether",
    "jobot",
    "kelly services",
    "kforce",
    "manpowergroup",
    "michael page",
    "modis",
    "motion recruitment",
    "page group",
    "phaidon international",
    "qualrecruit",
    "randstad",
    "recruiting from scratch",
    "recruiters",
    "recruitgo careers",
    "recruitlytixs hirings",
    "recruit lytixs hires",
    "recruits lab",
    "robert half",
    "signature consultants",
    "spade recruiting",
    "staffing solutions enterprises",
    "talent acquisition concepts",
    "talentbridge",
    "teksystems",
})


def is_staffing_agency(company: str | None) -> bool:
    """Return whether a company name matches a known staffing intermediary."""
    normalized = " ".join(str(company or "").casefold().split())
    return bool(normalized) and any(name in normalized for name in STAFFING_AGENCY_NAMES)
