"""Leadership level and IC seniority of a job title, and the bounds saved roles set.

Pure title vocabulary shared by the board (which hides rows outside the saved
roles' bounds) and search consolidation (which must never fold a saved role
into a query whose results those same bounds would hide). Imports nothing
above core.
"""

from __future__ import annotations

import re

from job_finder.title_aliases import expand_title_abbreviations

ROLE_TOKEN_ALIASES = {
    "architectural": "architect",
    "engineering": "engineer",
    "centers": "center",
    "centres": "centre",
    "mgr": "manager",
    "operations": "ops",
    "products": "product",
    "programs": "program",
    "projects": "project",
    "scientist": "science",
    "scientists": "science",
    "stewardship": "steward",
    "sr": "senior",
    "jr": "junior",
}
ROLE_FILLER_TOKENS = frozenset({"a", "an", "and", "of", "the"})


def role_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+", expand_title_abbreviations(value)):
        if raw in ROLE_FILLER_TOKENS:
            continue
        tokens.add(ROLE_TOKEN_ALIASES.get(raw, raw))
    return tokens


# Leadership levels, lowest first. A title's level is the highest one it
# names ("Senior Vice President, Data" is vp). "officer" only counts behind
# "chief", which is in the bucket already, so "Data Protection Officer" stays
# an individual contributor. role_tokens already folds "mgr" into "manager";
# "vice president" is two words, so title_level matches it as a phrase.
LEVEL_VOCABULARY: tuple[tuple[str, frozenset[str]], ...] = (
    ("lead", frozenset({"lead"})),
    ("manager", frozenset({"manager"})),
    ("director", frozenset({"director", "head"})),
    ("vp", frozenset({"vp", "svp", "evp"})),
    ("chief", frozenset({"chief", "cto", "cdo", "cio"})),
)
TITLE_LEVELS: tuple[str, ...] = tuple(name for name, _ in LEVEL_VOCABULARY)
_VICE_PRESIDENT_RE = re.compile(r"\bvice[\s-]+president\b")


def title_level(title: str | None) -> str | None:
    """The leadership level a title names (lead, manager, director, vp or
    chief), or None for an individual-contributor title."""
    tokens = role_tokens(title)
    if _VICE_PRESIDENT_RE.search(str(title or "").lower()):
        tokens = tokens | {"vp"}
    for level, words in reversed(LEVEL_VOCABULARY):
        if tokens & words:
            return level
    return None


def wanted_levels(terms: list[str]) -> set[str | None]:
    return {title_level(term) for term in terms}


# Individual-contributor seniorities, lowest first. "plain" is an IC title
# with none of these words. role_tokens folds "sr" into "senior" and "jr"
# into "junior"; the digits catch "Data Engineer 2".
IC_SENIORITY_VOCABULARY: tuple[tuple[str, frozenset[str]], ...] = (
    ("junior", frozenset({"junior", "entry", "intern", "associate", "i", "ii", "1", "2"})),
    ("plain", frozenset()),
    ("senior", frozenset({"senior"})),
    ("staff", frozenset({"staff", "principal", "distinguished"})),
)
IC_SENIORITIES: tuple[str, ...] = tuple(name for name, _ in IC_SENIORITY_VOCABULARY)


def ic_seniority(title: str | None) -> str | None:
    """The seniority an individual-contributor title names (junior, plain,
    senior or staff), or None for a leadership title."""
    if title_level(title) is not None:
        return None
    tokens = role_tokens(title)
    for seniority, words in reversed(IC_SENIORITY_VOCABULARY):
        if tokens & words:
            return seniority
    return "plain"


def wanted_ic_seniorities(terms: list[str]) -> set[str]:
    """The IC seniorities the saved roles admit. A role with a seniority word
    admits that seniority and above ("Staff Data Engineer" admits staff and
    principal, not the 100 plain "Data Engineer" rows a manager once got);
    a plain role admits every one."""
    admitted: set[str] = set()
    for term in terms:
        seniority = ic_seniority(term)
        if seniority is None:
            continue
        floor = 0 if seniority == "plain" else IC_SENIORITIES.index(seniority)
        admitted.update(IC_SENIORITIES[floor:])
    return admitted


def title_bound_exclusion(
    title: str | None, levels: set[str | None], seniorities: set[str]
) -> str | None:
    """Which saved-role bound excludes ``title``: "level", "seniority" or None."""
    level = title_level(title)
    if levels and level not in levels:
        return "level"
    if level is None and seniorities and ic_seniority(title) not in seniorities:
        return "seniority"
    return None


def saved_roles_reject(title: str | None, saved_roles: list[str]) -> bool:
    """True when the saved roles' own level/seniority bounds hide ``title``."""
    return title_bound_exclusion(
        title, wanted_levels(saved_roles), wanted_ic_seniorities(saved_roles)
    ) is not None
