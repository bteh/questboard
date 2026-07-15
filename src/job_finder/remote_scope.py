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


def classify_remote_scope(location: str | None) -> str:
    """The stated scope of a location text; "" when nothing usable is stated."""
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
