"""Job-title abbreviations that stand for a whole phrase.

One table read by both the pull (scrapers' role filter) and the board (lane
check and SQL title prefilter), so a title the pull keeps is a title the board
shows. Abbreviations match as whole words only.
"""

from __future__ import annotations

import re

# "bi": "BI Engineering, Manager" (Evercommerce) and "Power BI Manager" missed
# the saved role "Manager, Business Intelligence" (Oct 12 2026 board audit).
# "BIM Manager" is building information modeling and stays as written.
# "pipeline(s)": Supabase "Engineering Manager - Pipelines" (Nov 12 2026) is a
# data replication team but never says "data". See EXPANSION_BLOCKERS.
TITLE_ABBREVIATIONS: dict[str, str] = {
    "bi": "business intelligence",
    "pipeline": "data pipeline",
    "pipelines": "data pipelines",
}

# The word right before an abbreviation that keeps it as written. CI/CD,
# build, sales and rendering pipelines are not data work.
_NOT_DATA_PIPELINE = frozenset({
    "data", "ci", "cd", "cicd", "build", "builds", "release", "deployment",
    "deploy", "delivery", "devops", "test", "testing", "sales", "revenue",
    "deal", "deals", "talent", "recruiting", "hiring", "candidate", "rendering",
    "graphics", "asset", "assets", "content", "art", "animation", "vfx", "drug",
    "clinical",
})
EXPANSION_BLOCKERS: dict[str, frozenset[str]] = {
    "pipeline": _NOT_DATA_PIPELINE,
    "pipelines": _NOT_DATA_PIPELINE,
}

_ABBREVIATION_RE = re.compile(
    r"\b(" + "|".join(re.escape(key) for key in TITLE_ABBREVIATIONS) + r")\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _expand(match: re.Match[str]) -> str:
    key = match.group(1).lower()
    before = _WORD_RE.findall(match.string[: match.start()])
    if before and before[-1] in EXPANSION_BLOCKERS.get(key, ()):
        return match.group(0)
    return TITLE_ABBREVIATIONS[key]


def expand_title_abbreviations(text: str | None) -> str:
    """``text`` with each whole-word abbreviation spelled out, lowercased."""
    return _ABBREVIATION_RE.sub(_expand, str(text or "").lower())


def abbreviations_for(word: str) -> tuple[str, ...]:
    """The abbreviations whose expansion contains ``word``, so a SQL prefilter
    on "intelligence" can also retrieve titles that only say "BI"."""
    lowered = word.lower()
    return tuple(
        key for key, phrase in TITLE_ABBREVIATIONS.items() if lowered in phrase.split()
    )
