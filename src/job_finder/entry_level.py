"""Entry-level detection: every rule for "can someone breaking in apply?"

Real case (Oct 8 2026): a seeker who lost an IT job wanted analyst and IT
support roles he could land without years of seniority. Find Work was tuned
for a senior leadership search and had no way to show entry roles. Each rule
here is pinned by a test in tests/test_entry_level.py that names the posting
title or description line that motivated it.

Order: a senior title word or an upper tier ("Technician 4", "Tier 2")
disqualifies, then a description demanding five or
more years disqualifies, then any title rule or description rule qualifies.
"""

from __future__ import annotations

import re

TITLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("junior", re.compile(r"\b(?:junior|jr)\b\.?", re.I)),
    ("associate", re.compile(r"\bassociate\b", re.I)),
    ("entry", re.compile(r"\bentry[\s-]*level\b|\bentry\b", re.I)),
    ("level one", re.compile(r"\blevel[\s-]*(?:i|1|one)\b", re.I)),
    ("trailing I or 1", re.compile(r"\s(?:I|1)\s*(?:$|[-,(/|–])")),
    ("trainee", re.compile(r"\btrainee\b", re.I)),
    ("apprentice", re.compile(r"\bapprentice(?:ship)?\b", re.I)),
    ("assistant", re.compile(r"\bassistant\b", re.I)),
    ("technician", re.compile(r"\btechnician\b", re.I)),
    ("tier 1", re.compile(r"\btier[\s-]*(?:i|1|one)\b", re.I)),
    ("help desk", re.compile(r"\bhelp[\s-]*desk\b", re.I)),
    ("intern to hire", re.compile(r"\bintern[\s-]+to[\s-]+hire\b", re.I)),
)

DESCRIPTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("0-2 years", re.compile(
        r"\b(?:0|1)\s*(?:-|–|to)\s*[1-3]\+?\s*(?:years?|yrs?)\b", re.I,
    )),
    ("1+ year", re.compile(
        r"(?<![\d.])(?:1|one)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?\s+(?:[\w-]+\s+){0,4}experience", re.I,
    )),
    ("entry level", re.compile(r"\bentry[\s-]+level\b", re.I)),
    ("new grad", re.compile(r"\b(?:new|recent)\s+grad(?:uate)?s?\b", re.I)),
    ("no experience required", re.compile(
        r"\bno\s+(?:prior\s+|previous\s+)?experience\s+(?:is\s+)?(?:required|necessary|needed)\b", re.I,
    )),
)

SENIOR_TITLE_WORDS = re.compile(
    r"\b(?:senior|sr|lead|principal|staff|manager|director|head|vp|chief|president|"
    r"supervisor|architect|partner|counsel|ii|iii|iv)\b",
    re.I,
)
UPPER_TIER_TITLE = re.compile(
    r"\b(?:tier|level)[\s-]*(?:[2-9]|two|three)\b|\s[2-9]\s*(?:$|[-,(/|–])",
    re.I,
)

_WORD_NUMBERS = {
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
_WORD_NUMBER_RE = re.compile(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", re.I)
_YEARS_RE = re.compile(
    r"(?<![\d.$])(\d{1,2})\s*(\+|plus|or\s+more)?\s*"
    r"(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b([^.;\n]{0,60})",
    re.I,
)
SENIOR_YEARS = 5


def demands_senior_years(description: str | None) -> bool:
    """True when a description asks for five or more years. A range counts
    by its floor, so "3-5 years" stays open and "5-7 years" does not."""
    text = _WORD_NUMBER_RE.sub(lambda m: _WORD_NUMBERS[m.group(1).lower()], str(description or ""))
    for match in _YEARS_RE.finditer(text):
        floor = int(match.group(1))
        if floor < SENIOR_YEARS or floor > 30:
            continue
        if match.group(2) or "experience" in match.group(3).lower():
            return True
    return False


def entry_level_reason(title: str | None, description: str | None = None) -> str | None:
    """The rule that marks a posting entry level, or None."""
    title_text = str(title or "")
    if SENIOR_TITLE_WORDS.search(title_text) or UPPER_TIER_TITLE.search(title_text):
        return None
    if demands_senior_years(description):
        return None
    for name, pattern in TITLE_RULES:
        if pattern.search(title_text):
            return f"title: {name}"
    description_text = str(description or "")
    for name, pattern in DESCRIPTION_RULES:
        if pattern.search(description_text):
            return f"description: {name}"
    return None


def is_entry_level(title: str | None, description: str | None = None) -> bool:
    return entry_level_reason(title, description) is not None
