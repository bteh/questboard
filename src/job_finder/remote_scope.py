"""Classify a posting's stated remote scope from its location text.

Remote does not mean remote-for-you: sources routinely state "Remote, India"
or "Remote (UK Based only)". The place filter uses this classification so a
US place filter stops passing remote rows a US person cannot take.

Scopes:
- "us"        the wording names the US (or parses to a US state/city)
- "worldwide" the wording says anywhere/worldwide/global
- "intl"      the wording names only non-US countries/regions
- ""          nothing stated beyond remote-ish words; conservatively kept

The classifier only ever acts on what the text states. Ambiguous wording
returns "" and is never excluded.

Some sources put the region in the title instead: Arbeitnow listed KD Pharma
"Business Intelligence Manager (m/f/d) | Remote (Europe) | Full-time" at
"Bexbach". When the location states nothing, an explicit remote/region
qualifier in the title decides (title_remote_qualifier).
"""

from __future__ import annotations

import re

from job_finder.us_states import state_codes_field

_US_RE = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|us|nationwide|north america|americas)\b",
    re.IGNORECASE,
)

_WORLDWIDE_RE = re.compile(r"\b(worldwide|anywhere|global)\b", re.IGNORECASE)

# Non-US countries, regions, and the foreign hub cities that appear in job
# location fields. Word-boundary matched, case-insensitive. Extend freely:
# a miss only means a row is conservatively kept, never wrongly hidden.
_INTL_TOKENS = (
    "europe", "emea", "eu", "united kingdom", "uk", "england", "scotland",
    "ireland", "london", "germany", "berlin", "munich", "france", "paris",
    "netherlands", "amsterdam", "spain", "barcelona", "madrid", "portugal",
    "lisbon", "poland", "warsaw", "czech", "prague", "switzerland", "zurich",
    "norway", "sweden", "stockholm", "denmark", "copenhagen", "finland",
    "italy", "milan", "rome", "austria", "vienna", "greece", "romania",
    "ukraine", "estonia", "latvia", "lithuania", "hungary", "budapest",
    "canada", "toronto", "vancouver", "montreal", "ontario",
    "mexico", "guadalajara", "monterrey", "latam", "latin america", "brazil",
    "sao paulo", "argentina", "buenos aires", "chile", "colombia", "bogota",
    "peru", "costa rica", "guatemala", "uruguay", "ecuador",
    "india", "bangalore", "bengaluru", "hyderabad", "mumbai", "delhi", "pune",
    "chennai", "noida", "gurgaon", "apac", "asia", "singapore", "japan",
    "tokyo", "china", "shanghai", "beijing", "hong kong", "taiwan", "taipei",
    "south korea", "seoul", "philippines", "manila", "vietnam", "indonesia",
    "jakarta", "thailand", "bangkok", "malaysia", "pakistan", "bangladesh",
    "sri lanka", "nepal",
    "australia", "sydney", "melbourne", "new zealand", "auckland",
    "israel", "tel aviv", "turkey", "istanbul", "uae", "dubai", "abu dhabi",
    "united arab emirates", "saudi arabia", "qatar", "egypt", "cairo",
    "nigeria", "lagos", "kenya", "nairobi", "south africa", "cape town",
    "johannesburg", "ghana", "morocco",
)
_INTL_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _INTL_TOKENS) + r")\b",
    re.IGNORECASE,
)


# Title qualifiers: "Remote (Europe)", "Remote - EMEA", "Remote, India", and a
# bare bracketed region like "(UK)". The captured text must then be made only
# of region names, so "Remote - European Markets" or "(m/f/d)" never scope.
_TITLE_REMOTE_BRACKET_RE = re.compile(r"\bremote\s*[(\[]([^)\]]{1,40})[)\]]", re.IGNORECASE)
_TITLE_REMOTE_TAIL_RE = re.compile(
    r"\bremote\s*(?:[-\u2013\u2014:,]|\bin\b)\s*([^|()\[\];]{1,40})", re.IGNORECASE,
)
_TITLE_BRACKET_RE = re.compile(r"[(\[]([^)\]]{1,40})[)\]]")
_QUALIFIER_FILLER_RE = re.compile(
    r"\b(remote|remotely|fully|only|based|in|within|from|first|work|wfh)\b", re.IGNORECASE,
)
_QUALIFIER_SPLIT_RE = re.compile(r"\s*(?:/|,|&|\+|\band\b|\bor\b)\s*", re.IGNORECASE)


def _is_region_only(text: str) -> bool:
    remainder = _QUALIFIER_FILLER_RE.sub(" ", text)
    remainder = re.sub(r"[-\u2013\u2014:.]", " ", remainder)
    parts = [" ".join(p.split()) for p in _QUALIFIER_SPLIT_RE.split(remainder)]
    parts = [p for p in parts if p]
    if not parts:
        return False
    return all(
        _US_RE.fullmatch(p) or _WORLDWIDE_RE.fullmatch(p) or _INTL_RE.fullmatch(p)
        for p in parts
    )


def _title_qualifier(title: str | None) -> tuple[str, bool]:
    text = (title or "").strip()
    if not text:
        return "", False
    for pattern in (_TITLE_REMOTE_BRACKET_RE, _TITLE_REMOTE_TAIL_RE, _TITLE_BRACKET_RE):
        for match in pattern.finditer(text):
            candidate = match.group(1).strip()
            if _is_region_only(candidate):
                return candidate, pattern is not _TITLE_BRACKET_RE
    return "", False


def title_remote_qualifier(title: str | None) -> str:
    """The region text a title states for its remote scope; "" when none.

    Conservative on purpose: only a remote qualifier or a bracketed region
    counts, so "Data Team Lead, EMEA" and "European Markets Analyst" say
    nothing about where the remote work may happen.
    """
    return _title_qualifier(title)[0]


def title_states_remote(title: str | None) -> bool:
    """True when the title says "Remote (<region>)" or "Remote - <region>".

    A bare "remote" word is not enough ("Remote Sensing Analyst").
    """
    return _title_qualifier(title)[1]


def classify_remote_scope(location: str | None, title: str | None = None) -> str:
    """The stated scope of a posting; "" when nothing usable is stated.

    The location decides when it states a scope; the title is read only when
    the location is silent.
    """
    scope = _classify_location(location)
    if scope or not title:
        return scope
    return _classify_location(title_remote_qualifier(title))


def _classify_location(location: str | None) -> str:
    text = (location or "").strip()
    if not text:
        return ""
    # A US signal wins over anything else in the same text: a mixed list
    # ("Canada, United States") is reachable from the US.
    if _US_RE.search(text) or state_codes_field(text):
        return "us"
    if _WORLDWIDE_RE.search(text):
        return "worldwide"
    if _INTL_RE.search(text):
        return "intl"
    return ""
