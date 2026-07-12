"""US state names and abbreviations, for the place filter's structured
state matching.

A typed "Georgia" should find rows whose location says "GA" (bank
bonuses state their availability as abbreviation lists), and a typed
"GA" should find "Georgia". Nothing here guesses geography; it only
teaches the filter that two spellings of the same state are the same
state, and it extracts the states a location string actually names so
matching is a clean token lookup instead of prose substring guessing.

Why parse at ingest instead of tokenizing in SQL at query time: a
query-time review (2026-07-12) found that SQL string normalization
cannot safely tell an availability list ("VA & NC only") from prose
("we work from our office in Austin, TX", where "in" is not Indiana),
nor keep "Virginia" from matching "West Virginia" by substring. Python
with word boundaries and a capitalization rule can. extract_state_codes
runs once per row at save time; the filter matches a pre-tokenized field.
"""

from __future__ import annotations

import re

STATE_TO_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC",
}

ABBR_TO_STATE: dict[str, str] = {}
for _name, _abbr in STATE_TO_ABBR.items():
    # first name wins ("district of columbia" over "washington dc")
    ABBR_TO_STATE.setdefault(_abbr, _name)


def state_aliases(place: str) -> tuple[str, str] | None:
    """(full name, abbreviation) when the typed place IS a state, else None."""
    cleaned = place.strip().lower().replace(".", "")
    if cleaned in STATE_TO_ABBR:
        return cleaned, STATE_TO_ABBR[cleaned]
    upper = cleaned.upper()
    if len(upper) == 2 and upper in ABBR_TO_STATE:
        return ABBR_TO_STATE[upper], upper
    return None


# spelled-out names, longest first so "west virginia" is consumed before
# "virginia" can rematch, and "new york" before any short overlap
_NAMES_LONGEST_FIRST = sorted(STATE_TO_ABBR.items(), key=lambda kv: -len(kv[0]))
_NAME_RES = [(re.compile(rf"\b{re.escape(name)}\b"), abbr) for name, abbr in _NAMES_LONGEST_FIRST]
# 2-letter tokens; validated against real codes. Applied to the ORIGINAL
# (case-preserved) string so lowercase prose words ("in", "or", "me") are
# never mistaken for AL/CT-style codes, which availability lists capitalize.
_CODE_RE = re.compile(r"\b[A-Z]{2}\b")
_VALID_CODES = set(ABBR_TO_STATE)


def extract_state_codes(location: str | None) -> list[str]:
    """The US states a location string names, as sorted 2-letter codes.

    Spelled-out names match case-insensitively on word boundaries
    (longest first, so "West Virginia" yields WV and not VA). Bare codes
    must be UPPERCASE in the source, which is how bank-bonus availability
    lists are written ("AL, CT, D.C., MD, VA Only") and which keeps
    lowercase prose ("office in Austin, TX" -> TX only) out. Returns []
    when no US state is named (a foreign city, a placeless row).
    """
    if not location:
        return []
    found: set[str] = set()

    lowered = location.lower()
    for pattern, abbr in _NAME_RES:
        if pattern.search(lowered):
            found.add(abbr)
            lowered = pattern.sub(" ", lowered)  # consume the span

    # "D.C." -> "DC" so the code regex sees it as one token
    coded = location.replace(".", "")
    for token in _CODE_RE.findall(coded):
        if token in _VALID_CODES:
            found.add(token)

    return sorted(found)


def state_codes_field(location: str | None) -> str:
    """Comma-wrapped codes for the DB (",AL,CT,VA," or ""), for clean
    token matching: ``state_codes LIKE '%,VA,%'`` never false-positives."""
    codes = extract_state_codes(location)
    return ("," + ",".join(codes) + ",") if codes else ""
