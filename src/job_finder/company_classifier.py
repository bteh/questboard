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
# Location parsing and filtering
# =========================================================================

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_REMOTE_KEYWORDS = {"remote", "work from home", "wfh", "anywhere", "distributed"}


def parse_location(raw_location: str, is_remote: bool = False) -> dict:
    """Parse a raw location string into {city, state, is_remote}."""
    result: dict = {"city": "", "state": "", "is_remote": is_remote}

    if not raw_location:
        return result

    loc = raw_location.strip()
    loc_lower = loc.lower()

    # Detect remote
    for kw in _REMOTE_KEYWORDS:
        if kw in loc_lower:
            result["is_remote"] = True
            break

    # Strip remote/hybrid noise to find underlying city
    cleaned = re.sub(
        r"\b(remote|hybrid|work from home|wfh|anywhere|distributed)\b",
        "",
        loc,
        flags=re.IGNORECASE,
    )
    # Strip country suffixes
    cleaned = re.sub(
        r",?\s*\b(United States|US|USA|U\.S\.)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" ,-()/")

    # Try "City, ST" or "City, ST ZIP"
    match = re.match(r"^([A-Za-z\s.'-]+),\s*([A-Z]{2})\b", cleaned.strip())
    if match:
        result["city"] = match.group(1).strip()
        result["state"] = match.group(2).strip()
        return result

    # Try just a 2-letter state code
    match = re.match(r"^([A-Z]{2})$", cleaned.strip())
    if match and match.group(1) in _US_STATES:
        result["state"] = match.group(1)
        return result

    return result


def location_matches_preferences(
    job_location: str,
    is_remote: bool,
    preferred_states: list[str] | None = None,
    preferred_cities: list[str] | None = None,
) -> bool:
    """Check if a job location matches user preferences.

    Rules:
    1. Remote jobs ALWAYS pass.
    2. If job's state matches any preferred state -> pass.
    3. If job's city matches any preferred city (substring) -> pass.
    4. If no preferences configured -> pass (no filtering).
    """
    # No preferences = no filtering
    if not preferred_states and not preferred_cities:
        return True

    parsed = parse_location(job_location, is_remote)

    # Rule 1: Remote always passes
    if parsed["is_remote"]:
        return True

    # Rule 2: State match
    if preferred_states and parsed["state"]:
        if parsed["state"].upper() in [s.upper() for s in preferred_states]:
            return True

    # Rule 3: City match (substring, case-insensitive)
    if preferred_cities and parsed["city"]:
        city_lower = parsed["city"].lower()
        for pref_city in preferred_cities:
            if pref_city.lower() in city_lower or city_lower in pref_city.lower():
                return True

    # No match
    return False
