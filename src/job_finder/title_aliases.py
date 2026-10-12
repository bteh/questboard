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
TITLE_ABBREVIATIONS: dict[str, str] = {
    "bi": "business intelligence",
}

_ABBREVIATION_RE = re.compile(
    r"\b(" + "|".join(re.escape(key) for key in TITLE_ABBREVIATIONS) + r")\b",
    re.IGNORECASE,
)


def expand_title_abbreviations(text: str | None) -> str:
    """``text`` with each whole-word abbreviation spelled out, lowercased."""
    return _ABBREVIATION_RE.sub(
        lambda match: TITLE_ABBREVIATIONS[match.group(1).lower()],
        str(text or "").lower(),
    )


def abbreviations_for(word: str) -> tuple[str, ...]:
    """The abbreviations whose expansion contains ``word``, so a SQL prefilter
    on "intelligence" can also retrieve titles that only say "BI"."""
    lowered = word.lower()
    return tuple(
        key for key, phrase in TITLE_ABBREVIATIONS.items() if lowered in phrase.split()
    )
