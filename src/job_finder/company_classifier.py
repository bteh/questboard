"""Company type classification and location filtering utilities."""

from __future__ import annotations

import re

# =========================================================================
# Known-company lists (lowercase, normalized)
# =========================================================================

FAANG_PLUS = {
    "apple", "google", "alphabet", "amazon", "meta", "facebook",
    "microsoft", "nvidia", "netflix", "tesla",
}

BIG_TECH = {
    # Public tech giants
    "salesforce", "adobe", "uber", "lyft", "doordash", "instacart",
    "coinbase", "robinhood", "block", "square", "paypal",
    "shopify", "spotify", "snap", "pinterest", "reddit",
    "palantir", "datadog", "cloudflare", "crowdstrike", "mongodb",
    "twilio", "okta", "zscaler", "servicenow", "workday", "splunk",
    "atlassian", "vmware", "broadcom", "dell", "ibm", "cisco",
    "intel", "amd", "qualcomm", "oracle", "sap",
    "samsung", "sony", "tiktok", "bytedance",
    # Large public data/cloud companies
    "snowflake", "databricks", "confluent", "elastic", "hashicorp",
    "palo alto networks", "fortinet", "arista networks",
}

ELITE_STARTUPS = {
    # AI / ML
    "openai", "anthropic", "cohere", "mistral", "mistral ai",
    "hugging face", "scale ai", "runway", "stability ai",
    "perplexity", "character ai", "inflection",
    # Fintech / Infrastructure
    "stripe", "ramp", "brex", "plaid", "mercury", "rippling",
    "gusto", "carta", "anduril", "flexport",
    # Dev tools / Data
    "vercel", "supabase", "neon", "planetscale", "retool",
    "linear", "figma", "notion", "canva", "livekit",
    "dbt labs", "fivetran", "starburst", "clickhouse", "motherduck",
    "tabular", "dagster", "prefect", "airbyte", "meltano",
    # Consumer / Other unicorns
    "discord", "airbnb", "faire", "vanta", "loom",
    # Quant / HFT
    "citadel", "jane street", "hudson river trading", "two sigma",
    "de shaw", "jump trading", "tower research", "virtu financial",
}

# YC top companies for tagging
YC_COMPANIES = {
    "airbnb", "doordash", "coinbase", "instacart", "stripe", "dropbox",
    "twitch", "reddit", "gusto", "zapier", "gitlab", "brex", "faire",
    "cruise", "rappi", "matterport", "pagerduty", "fivetran", "vanta",
    "retool", "monzo", "razorpay", "ginkgo bioworks",
}

ENTERPRISE_COMPANIES = {
    # Finance
    "jpmorgan", "jp morgan", "goldman sachs", "bank of america",
    "wells fargo", "citigroup", "citi", "morgan stanley", "barclays",
    "capital one", "american express", "visa", "mastercard",
    # Consulting
    "deloitte", "mckinsey", "bcg", "bain", "accenture", "kpmg", "ey",
    "pwc", "pricewaterhousecoopers",
    # Healthcare / Pharma
    "johnson & johnson", "pfizer", "unitedhealth", "cvs health",
    "anthem", "humana", "kaiser", "cigna",
    # Retail / CPG
    "walmart", "target", "costco", "home depot", "procter & gamble",
    "coca-cola", "pepsico", "unilever",
    # Industrial / Defense
    "general electric", "boeing", "lockheed martin", "raytheon",
    "northrop grumman", "general dynamics",
    # Telecom / Media
    "at&t", "verizon", "comcast", "disney", "warner bros",
}

# =========================================================================
# Company name normalization
# =========================================================================

_STRIP_SUFFIXES = re.compile(
    r",?\s*\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|corporation|company|"
    r"incorporated|limited|group|holdings|technologies|technology|"
    r"software|labs|the)\b\.?",
    re.IGNORECASE,
)


def _normalize_company_name(name: str) -> str:
    """Normalize a company name for matching."""
    name = name.strip().lower()
    name = _STRIP_SUFFIXES.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


# =========================================================================
# Parsing helpers
# =========================================================================

def _parse_employee_count(raw: str | None) -> int | None:
    """Parse employee count strings like '200-500', '~300', '10001+'."""
    if not raw:
        return None
    raw = raw.strip().replace(",", "").replace("~", "").replace(" ", "")

    # "10001+" or "10000+"
    if "+" in raw:
        try:
            return int(raw.replace("+", ""))
        except ValueError:
            return None

    # "200-500" -> midpoint
    if "-" in raw:
        parts = raw.split("-")
        try:
            lo, hi = int(parts[0]), int(parts[1])
            return (lo + hi) // 2
        except (ValueError, IndexError):
            return None

    # Plain number
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_funding_amount(raw: str | None) -> float | None:
    """Parse funding strings like '$50M', '$1.2B', '50000000'."""
    if not raw:
        return None
    raw = raw.strip().replace(",", "").replace("$", "")

    multiplier = 1
    raw_upper = raw.upper()
    if raw_upper.endswith("B"):
        multiplier = 1_000_000_000
        raw = raw[:-1]
    elif raw_upper.endswith("M"):
        multiplier = 1_000_000
        raw = raw[:-1]
    elif raw_upper.endswith("K"):
        multiplier = 1_000
        raw = raw[:-1]

    try:
        return float(raw) * multiplier
    except ValueError:
        return None


# =========================================================================
# Classification
# =========================================================================

COMPANY_TYPES = [
    "FAANG+", "Big Tech", "Elite Startup", "Growth Stage",
    "Early Startup", "Midsize", "Enterprise", "Unknown",
]


def classify_company(
    company_name: str,
    funding_stage: str | None = None,
    total_funding: str | None = None,
    employee_count: str | None = None,
) -> str:
    """Classify a company into a type tier.

    Priority: known-list > funding heuristic > employee count > Unknown.
    """
    normalized = _normalize_company_name(company_name)

    # 1. Known-list matching
    if normalized in FAANG_PLUS:
        return "FAANG+"

    if normalized in BIG_TECH:
        return "Big Tech"

    if normalized in ELITE_STARTUPS:
        return "Elite Startup"

    if normalized in ENTERPRISE_COMPANIES:
        return "Enterprise"

    # 2. Funding stage heuristics
    if funding_stage:
        stage = funding_stage.lower().replace("-", " ").strip()

        if stage in ("ipo", "public"):
            emp = _parse_employee_count(employee_count)
            if emp and emp >= 1000:
                return "Big Tech"
            return "Midsize"

        if any(s in stage for s in ("series d", "series e", "series f", "series g")):
            return "Elite Startup"

        funding_amt = _parse_funding_amount(total_funding)
        if funding_amt and funding_amt >= 500_000_000:
            return "Elite Startup"

        if any(s in stage for s in ("series b", "series c")):
            if funding_amt and funding_amt >= 100_000_000:
                return "Elite Startup"
            return "Growth Stage"

        if "series a" in stage:
            emp = _parse_employee_count(employee_count)
            if emp and emp > 100:
                return "Growth Stage"
            return "Early Startup"

        if any(s in stage for s in ("seed", "pre-seed", "pre seed", "angel", "bootstrap")):
            return "Early Startup"

    # 3. Employee count fallback
    emp = _parse_employee_count(employee_count)
    if emp is not None:
        if emp >= 10_000:
            return "Enterprise"
        if emp >= 1_000:
            return "Midsize"
        if emp >= 200:
            return "Growth Stage"  # could be midsize or growth
        if emp >= 50:
            return "Growth Stage"
        return "Early Startup"

    # 4. Funding amount alone
    funding_amt = _parse_funding_amount(total_funding)
    if funding_amt is not None:
        if funding_amt >= 100_000_000:
            return "Elite Startup"
        if funding_amt >= 10_000_000:
            return "Growth Stage"
        return "Early Startup"

    return "Unknown"


# =========================================================================
# Metro area mapping (cities that belong to the same metro / commute zone)
# =========================================================================

METRO_AREAS: dict[str, set[str]] = {
    "Los Angeles": {"los angeles", "santa monica", "culver city", "burbank", "pasadena", "glendale", "long beach", "torrance", "el segundo", "playa vista", "marina del rey", "venice", "west hollywood", "beverly hills", "inglewood", "hawthorne", "manhattan beach", "hermosa beach", "redondo beach", "irvine", "costa mesa", "anaheim", "santa ana", "huntington beach", "newport beach", "woodland hills", "encino", "sherman oaks"},
    "San Francisco": {"san francisco", "san jose", "oakland", "palo alto", "mountain view", "sunnyvale", "santa clara", "cupertino", "menlo park", "redwood city", "san mateo", "fremont", "berkeley", "emeryville", "south san francisco", "foster city", "milpitas", "campbell", "los gatos", "saratoga"},
    "New York": {"new york", "brooklyn", "manhattan", "queens", "bronx", "staten island", "jersey city", "hoboken", "newark", "white plains", "stamford", "yonkers"},
    "Seattle": {"seattle", "bellevue", "redmond", "kirkland", "tacoma", "bothell", "renton", "kent", "everett"},
    "Boston": {"boston", "cambridge", "somerville", "quincy", "brookline", "waltham", "newton", "lexington", "burlington"},
    "Austin": {"austin", "round rock", "cedar park", "pflugerville", "georgetown", "san marcos", "kyle"},
    "Chicago": {"chicago", "evanston", "schaumburg", "naperville", "arlington heights", "skokie", "oak brook"},
    "Denver": {"denver", "boulder", "aurora", "lakewood", "littleton", "broomfield", "westminster", "englewood"},
    "San Diego": {"san diego", "la jolla", "chula vista", "carlsbad", "encinitas", "oceanside"},
    "Washington": {"washington", "arlington", "alexandria", "bethesda", "silver spring", "tysons", "reston", "mclean", "fairfax"},
    "Miami": {"miami", "fort lauderdale", "hollywood", "coral gables", "boca raton", "doral", "aventura"},
    "Atlanta": {"atlanta", "decatur", "marietta", "alpharetta", "sandy springs", "roswell", "dunwoody"},
    "Dallas": {"dallas", "fort worth", "plano", "frisco", "irving", "arlington", "richardson", "addison"},
    "Portland": {"portland", "beaverton", "hillsboro", "lake oswego", "tigard"},
    "Minneapolis": {"minneapolis", "st paul", "saint paul", "bloomington", "eden prairie", "plymouth"},
    "Pittsburgh": {"pittsburgh", "carnegie mellon", "oakland"},
    "Detroit": {"detroit", "ann arbor", "dearborn", "troy", "southfield"},
    "Philadelphia": {"philadelphia", "king of prussia", "conshohocken", "cherry hill", "camden"},
    "Raleigh": {"raleigh", "durham", "chapel hill", "cary", "morrisville", "research triangle"},
    "Salt Lake City": {"salt lake city", "provo", "sandy", "draper", "lehi", "orem"},
}


def _find_metro(city: str) -> str | None:
    """Given a city name, return the metro area it belongs to (or None)."""
    city_lower = city.lower().strip()
    for metro, cities in METRO_AREAS.items():
        if city_lower in cities:
            return metro
    return None


# =========================================================================
# Location parsing and filtering
# =========================================================================

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_STATE_NAME_TO_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

# Common non-US countries/regions that appear in job locations
_NON_US_COUNTRIES = {
    "india", "canada", "uk", "united kingdom", "germany", "france", "brazil",
    "australia", "japan", "china", "singapore", "ireland", "netherlands",
    "mexico", "israel", "sweden", "spain", "italy", "poland", "argentina",
    "colombia", "chile", "portugal", "switzerland", "austria", "belgium",
    "denmark", "finland", "norway", "south korea", "taiwan", "philippines",
    "vietnam", "thailand", "indonesia", "malaysia", "new zealand", "czech republic",
    "romania", "hungary", "ukraine", "turkey", "egypt", "south africa", "nigeria",
    "kenya", "pakistan", "bangladesh", "sri lanka", "nepal", "costa rica",
    "united arab emirates", "uae", "saudi arabia", "qatar", "dubai",
}

_REMOTE_KEYWORDS = {"remote", "work from home", "wfh", "anywhere", "distributed"}
_HYBRID_KEYWORDS = {"hybrid", "in-office", "in office", "on-site", "onsite", "days in office", "office days"}
_ONSITE_KEYWORDS = {"on-site only", "onsite only", "in-person", "in person", "no remote"}

# Regex patterns that strongly indicate hybrid/in-office requirements in descriptions
_HYBRID_PATTERNS = [
    r"\d+\s*(?:days?|x)\s*(?:per|a|each|\/)\s*week\s*(?:in|at|from)?\s*(?:the\s+)?(?:office|on.?site)",
    r"(?:in|at|from)\s*(?:the\s+)?office\s*\d+\s*(?:days?|x)\s*(?:per|a|each|\/)\s*week",
    r"(?:office|on.?site)\s*(?:presence|attendance)\s*(?:required|expected|mandatory)",
    r"return\s+to\s+(?:the\s+)?office",
    r"(?:must|required to|expected to|need to)\s+(?:be\s+)?(?:in|at|come\s+to)\s+(?:the\s+)?office",
    r"(?:work|report)\s+(?:from|at|in)\s+(?:the|our)\s+(?:office|location|site|campus)",
    r"days?\s+(?:in|at)\s+(?:the\s+)?office",
    r"(?:in|at)\s+(?:the\s+)?office\s+(?:at\s+least|minimum)",
    r"flexible\s+(?:hybrid|work\s+arrangement)",
    r"combination\s+of\s+(?:remote|in.office|office)",
]


def parse_location(raw_location: str, is_remote: bool = False) -> dict:
    """Parse a raw location string into {city, state, is_remote}.

    Handles formats: "City, ST", "City, StateName", "City, State, Country",
    "Country, ST, City" (reversed), and non-US locations.  Returns
    ``country="non-us"`` when a known foreign country is detected.
    """
    result: dict = {"city": "", "state": "", "is_remote": is_remote, "country": ""}

    if not raw_location:
        return result

    loc = raw_location.strip()
    loc_lower = loc.lower()

    # Detect remote
    for kw in _REMOTE_KEYWORDS:
        if kw in loc_lower:
            result["is_remote"] = True
            break

    # Detect non-US countries early (before stripping)
    for country in _NON_US_COUNTRIES:
        # Match as whole word at end or as a comma-separated part
        if re.search(r"(?:^|,\s*)" + re.escape(country) + r"(?:\s*$|,)", loc_lower):
            result["country"] = "non-us"
            return result

    # Strip remote/hybrid noise to find underlying city
    cleaned = re.sub(
        r"\b(remote|hybrid|work from home|wfh|anywhere|distributed)\b",
        "",
        loc,
        flags=re.IGNORECASE,
    )
    # Strip country suffixes
    cleaned = re.sub(
        r",?\s*\b(United States of America|United States|US|USA|U\.S\.)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" ,-()/")

    # Try "City, ST" or "City, ST ZIP"
    match = re.match(r"^([A-Za-z\s.'-]+),\s*([A-Z]{2})\b", cleaned.strip())
    if match and match.group(2) in _US_STATES:
        result["city"] = match.group(1).strip()
        result["state"] = match.group(2).strip()
        result["country"] = "US"
        return result

    # Try "City, Full State Name" (e.g. "O'Fallon, Missouri")
    match = re.match(r"^([A-Za-z\s.'-]+),\s*([A-Za-z\s]+)$", cleaned.strip())
    if match:
        state_name = match.group(2).strip().lower()
        abbr = _STATE_NAME_TO_ABBR.get(state_name)
        if abbr:
            result["city"] = match.group(1).strip()
            result["state"] = abbr
            result["country"] = "US"
            return result

    # Try reversed "ST, City" or "Country, ST, City" format
    parts = [p.strip() for p in cleaned.split(",")]
    if len(parts) >= 2:
        # Check if any part is a 2-letter US state code
        for i, part in enumerate(parts):
            if part.upper() in _US_STATES and len(part.strip()) == 2:
                result["state"] = part.upper()
                result["country"] = "US"
                # City is the part after the state code, or before if reversed
                remaining = [p for j, p in enumerate(parts) if j != i and p.upper() not in _US_STATES and len(p) > 2]
                if remaining:
                    result["city"] = remaining[-1].strip()
                return result

    # Try just a 2-letter state code
    match = re.match(r"^([A-Z]{2})$", cleaned.strip())
    if match and match.group(1) in _US_STATES:
        result["state"] = match.group(1)
        result["country"] = "US"
        return result

    return result


def _has_physical_location(location: str) -> bool:
    """Check if the location string contains a real city/state (not just 'Remote')."""
    if not location:
        return False
    cleaned = re.sub(
        r"\b(remote|hybrid|work from home|wfh|anywhere|distributed)\b",
        "", location, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r",?\s*\b(United States|US|USA|U\.S\.)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" ,-()/")
    # Has a city/state if there's meaningful text left (e.g. "Durham, NC")
    return bool(re.search(r"[A-Za-z]{2,}", cleaned))


def _desc_has_hybrid_pattern(desc_lower: str) -> bool:
    """Check description for hybrid/in-office requirement patterns."""
    # Check simple keywords first
    for kw in _HYBRID_KEYWORDS:
        if kw in desc_lower:
            return True
    # Check regex patterns for more nuanced phrases
    for pattern in _HYBRID_PATTERNS:
        if re.search(pattern, desc_lower):
            return True
    return False


def classify_work_type(
    location: str,
    description: str = "",
    is_remote_hint: bool = False,
) -> str:
    """Classify a job as 'remote', 'hybrid', or 'onsite'.

    Checks both the location string and description for signals.
    Hybrid signals override remote signals (stricter classification).

    When the only remote signal comes from the job board's metadata
    (is_remote_hint) but the job has a physical location and no
    explicit 'fully remote' confirmation in the description, we
    scan the description more aggressively for hybrid/office patterns
    since job boards frequently mislabel hybrid jobs as remote.

    Returns
    -------
    'remote' | 'hybrid' | 'onsite'
    """
    loc_lower = location.lower() if location else ""
    desc_lower = description.lower()[:4000] if description else ""

    remote_in_location = any(kw in loc_lower for kw in _REMOTE_KEYWORDS)
    has_remote = is_remote_hint or remote_in_location
    has_hybrid = any(kw in loc_lower for kw in _HYBRID_KEYWORDS)
    has_onsite = any(kw in loc_lower for kw in _ONSITE_KEYWORDS)

    # Always scan description for hybrid/office signals
    if not has_hybrid and not has_onsite:
        has_hybrid = _desc_has_hybrid_pattern(desc_lower)

    # Look for explicit "fully remote" confirmation in description
    confirmed_remote_in_desc = bool(
        re.search(r"\b(fully\s+remote|100%?\s*remote|remote.first|permanently\s+remote|all.remote)\b", desc_lower)
    )
    if confirmed_remote_in_desc:
        has_remote = True

    # KEY FIX: When the only remote signal is from the job board's metadata
    # (is_remote_hint) and there's a physical location like "Durham, NC",
    # be skeptical. Job boards frequently mislabel hybrid jobs as remote.
    # Require confirmation from the description or location text itself.
    hint_only_remote = is_remote_hint and not remote_in_location and not confirmed_remote_in_desc
    if hint_only_remote and _has_physical_location(location):
        # The board says remote but the posting has a specific city —
        # downgrade to hybrid unless description explicitly says remote.
        if has_hybrid:
            return "hybrid"
        # Even without hybrid keywords, a physical location + no remote
        # confirmation in the text is suspicious — call it hybrid.
        return "hybrid"

    # Hybrid overrides remote (if location says both "remote" and "hybrid",
    # it's hybrid — e.g. "Remote / Hybrid in San Francisco")
    if has_hybrid:
        return "hybrid"
    if has_onsite:
        return "onsite"
    if has_remote:
        return "remote"

    return "onsite"


def location_matches_preferences(
    job_location: str,
    is_remote: bool,
    preferred_states: list[str] | None = None,
    preferred_cities: list[str] | None = None,
    remote_only: bool = False,
    work_type: str = "",
) -> bool:
    """Check if a job location matches user preferences.

    Rules:
    1. If remote_only=True, only truly remote jobs pass (hybrid/onsite rejected).
    2. Fully remote jobs pass (unless they're actually hybrid).
    3. Hybrid and onsite jobs must match state/city preferences.
    4. If no preferences configured -> pass (no filtering).
    """
    # No preferences = no filtering
    if not preferred_states and not preferred_cities and not remote_only:
        return True

    # Use work_type if provided, otherwise fall back to basic detection
    wt = work_type or classify_work_type(job_location, "", is_remote)

    # Rule 1: remote_only mode — only truly remote passes
    if remote_only:
        return wt == "remote"

    # Rule 2: Fully remote passes (but NOT hybrid)
    if wt == "remote":
        return True

    # Rule 3: Hybrid and onsite must match state/city
    parsed = parse_location(job_location, is_remote)

    # Non-US locations: reject when user has US state/city preferences
    if parsed.get("country") == "non-us":
        return False

    # If location is empty or unparseable AND the raw string looks non-empty,
    # reject it — it's likely a foreign or unrecognized location.
    if not parsed["city"] and not parsed["state"]:
        # Truly empty location string → keep (benefit of the doubt)
        if not job_location or not job_location.strip():
            return True
        # Has text but couldn't parse → reject (likely non-US or unusual format)
        return False

    # City-level matching with metro area awareness
    if preferred_cities and parsed["city"]:
        job_city = parsed["city"].lower()
        job_metro = _find_metro(parsed["city"])
        for pref_city in preferred_cities:
            pref_lower = pref_city.lower()
            # Direct city match
            if pref_lower in job_city or job_city in pref_lower:
                return True
            # Metro area match: job's city is in the same metro as the preferred city
            pref_metro = _find_metro(pref_city)
            if pref_metro and pref_metro == job_metro:
                return True

    # State-level match — any job in a preferred state passes
    if preferred_states and parsed["state"]:
        if parsed["state"].upper() in [s.upper() for s in preferred_states]:
            return True

    # No match
    return False
