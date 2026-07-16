"""Shared helpers for scraper modules."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


_SEED_DIR = Path(__file__).parent / "data"


def _load_seed_slugs(filename: str) -> list[str]:
    """Load a newline-delimited slug list from scrapers/data/<filename>.

    Lines starting with '#' and blank lines are ignored. Used by ATS scrapers
    (Greenhouse, Lever, Ashby) to populate a default company list so that
    fresh users get startup coverage without configuring a watchlist.
    Returns [] if the file is missing — scrapers fall back gracefully.
    """
    path = _SEED_DIR / filename
    if not path.exists():
        return []
    seen: set[str] = set()
    slugs: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line not in seen:
            seen.add(line)
            slugs.append(line)
    return slugs


def _load_seed_section(filename: str, section_keyword: str) -> list[str]:
    """Load slugs from the ``# --- <section> ---`` block(s) matching a keyword.

    Seed files group slugs under section headers (e.g. ``# --- Crypto / web3 ---``).
    Returns the active (non-comment) slugs that fall under any header whose text
    contains ``section_keyword`` (case-insensitive), until the next header.
    Used to identify domain-specific companies (currently crypto/web3) so their
    jobs get domain-aware role matching.
    """
    path = _SEED_DIR / filename
    if not path.exists():
        return []
    slugs: list[str] = []
    in_section = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("# ---"):
            in_section = section_keyword.lower() in line.lower()
            continue
        if not line or line.startswith("#"):
            continue
        if in_section:
            slugs.append(line)
    return slugs


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_TIMEOUT = 15


def _get_json(
    url: str,
    params: dict | None = None,
    *,
    quiet_statuses: set[int] | None = None,
    timeout: int | float | None = None,
) -> dict | list | None:
    """GET a JSON endpoint with error handling.

    ``timeout`` overrides the module-level default (15s). Per-call control
    matters for ATS scrapers (Ashby/Greenhouse/Lever) which fan out to
    dozens of company boards in parallel — one slow company at 15s blocks
    a worker for far too long when most companies respond in <1s. Those
    callers pass a tighter timeout (e.g. 5s) so the pipeline fails fast
    on unreachable boards instead of stalling the whole search.
    """
    quiet_statuses = quiet_statuses or set()
    try:
        resp = requests.get(
            url,
            headers=_HEADERS,
            params=params,
            timeout=timeout if timeout is not None else _TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        log_fn = logger.debug if status in quiet_statuses else logger.warning
        log_fn("Failed to fetch %s: %s", url, e)
        return None
    except ValueError as e:
        logger.warning("Invalid JSON from %s: %s", url, e)
        return None


def _parse_salary(text: str | None) -> tuple[float | None, float | None]:
    """Extract min/max salary from a text string like '$120,000 - $180,000'."""
    if not text:
        return None, None
    matches = re.findall(r'\$?([\d,]+(?:\.\d+)?)\s*[kK]?', text)
    if len(matches) >= 2:
        lo = float(matches[0].replace(",", ""))
        hi = float(matches[1].replace(",", ""))
        if lo < 1000:
            lo *= 1000
        if hi < 1000:
            hi *= 1000
        return lo, hi
    elif len(matches) == 1:
        val = float(matches[0].replace(",", ""))
        if val < 1000:
            val *= 1000
        return val, None
    return None, None


def _parse_posted_date(raw: object) -> datetime | None:
    """Parse a job's posting date into a tz-aware UTC datetime, or None.

    Handles ISO8601 (with/without 'Z'), 'YYYY-MM-DD', and unix epoch
    seconds/milliseconds (RemoteOK/HN use epochs). Returns None on anything
    unparseable so callers can keep unknown-date jobs rather than drop them.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            val = float(raw)
            if val > 1e11:  # milliseconds
                val /= 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{9,13}", s):  # all-digit epoch
        try:
            val = float(s)
            if val > 1e11:
                val /= 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def date_confidence_for(raw: object, *, fuzzy: bool = False) -> str:
    """Confidence label for a scraper-provided posting date.

    Returns 'exact' when ``raw`` parses as a real posting date, 'fuzzy' when
    the caller only has an updated/approximate date (pass ``fuzzy=True``),
    and 'missing' when the value is absent or unparseable.
    """
    if _parse_posted_date(raw) is None:
        return "missing"
    return "fuzzy" if fuzzy else "exact"


_HOURS_PER_YEAR = 2080  # 40h x 52 weeks — standard annualization factor

# Number like 140000, 140,000, 140.5 — comma-grouped or plain.
_SAL_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SAL_SEP = r"\s*(?:-|–|—|to)\s*"
_SAL_HOURLY_SUFFIX = r"\s*(?:/\s*(?:hr|hour)\b|per\s+hour\b|an\s+hour\b|hourly\b)"

# One salary amount: optional $, the number, optional k suffix. The leading
# lookbehind keeps us from matching inside a larger token ("v2.140-170k").
_SAL_AMOUNT = rf"(?<![A-Za-z0-9,.])(\$)?\s*({_SAL_NUM})\s*([kK])?"

_SAL_RANGE_RE = re.compile(rf"{_SAL_AMOUNT}{_SAL_SEP}(\$)?\s*({_SAL_NUM})\s*([kK])?")
_SAL_BETWEEN_RE = re.compile(
    rf"between\s+{_SAL_AMOUNT}\s+and\s+(\$)?\s*({_SAL_NUM})\s*([kK])?",
    re.IGNORECASE,
)
_SAL_HOURLY_RANGE_RE = re.compile(
    rf"{_SAL_AMOUNT}{_SAL_SEP}(\$)?\s*({_SAL_NUM})\s*([kK])?{_SAL_HOURLY_SUFFIX}",
    re.IGNORECASE,
)
_SAL_HOURLY_SINGLE_RE = re.compile(
    rf"{_SAL_AMOUNT}{_SAL_HOURLY_SUFFIX}", re.IGNORECASE,
)
_SAL_UP_TO_RE = re.compile(rf"up\s+to\s+{_SAL_AMOUNT}", re.IGNORECASE)

# Text right after a candidate match that marks it as NOT a salary:
# percentages, durations, headcounts/traffic figures, 401(k) plans.
_SAL_BAD_TRAIL_RE = re.compile(
    r"^\s*(?:%|percent\b|years?\b|yrs?\b|\(?k\)|"
    r"bonus\b|stipend\b|sign[- ]?on\b|signing\b|"
    r"\+?\s*(?:users|customers|clients|employees|engineers|people|members|"
    r"hires|downloads|installs|requests|visitors|followers|subscribers)\b)",
    re.IGNORECASE,
)

# Money the COMPANY handles — budgets, revenue, funding rounds, valuations,
# transaction volume — not pay. A candidate range followed by one of these in
# the SAME clause is rejected ("a $140k-$170k marketing budget").
_SAL_BAD_CLAUSE_NOUN_RE = re.compile(
    r"\b(?:budgets?|revenues?|valuations?|funding|fundrais\w*|pre-?seed|"
    r"round|mrr|arr|gmv|transactions?)\b",
    re.IGNORECASE,
)
_SAL_CLAUSE_END_RE = re.compile(r"[.!?\n;:,]")

# Funding/revenue context directly BEFORE the amount ("raised a $500k…",
# "revenue up to $170k"). Anchored adjacent on purpose: "raised our salary
# bands to $140k" must still parse.
_SAL_BAD_LEAD_RE = re.compile(
    r"\b(?:rais(?:e[sd]?|ing)|valued\s+at|valuations?(?:\s+of)?|"
    r"budgets?\s+of|revenues?(?:\s+of)?|funding(?:\s+of)?|"
    r"mrr|arr|gmv)\s+(?:an?\s+)?$",
    re.IGNORECASE,
)

_SAL_ANNUAL_MIN = 20_000.0
_SAL_ANNUAL_MAX = 2_000_000.0
_SAL_HOURLY_MIN = 7.0
_SAL_HOURLY_MAX = 500.0


def _sal_value(num_str: str, has_k: bool, *, other_has_k: bool = False) -> float:
    """Normalize one captured amount to dollars ('140'+k -> 140000).

    ``other_has_k`` handles the '140-170k' shorthand where only the upper
    bound carries the k suffix.
    """
    val = float(num_str.replace(",", ""))
    if has_k or (other_has_k and val < 1000):
        val *= 1000
    return val


def _sal_context_ok(text: str, start: int, end: int) -> bool:
    """True unless nearby context marks the match as company money, not pay."""
    if _SAL_BAD_TRAIL_RE.match(text[end:end + 40]):
        return False
    trail_clause = _SAL_CLAUSE_END_RE.split(text[end:end + 60], 1)[0]
    if _SAL_BAD_CLAUSE_NOUN_RE.search(trail_clause):
        return False
    return not _SAL_BAD_LEAD_RE.search(text[max(0, start - 32):start])


def extract_salary_range(text: str | None) -> tuple[float | None, float | None]:
    """Extract an annual (salary_min, salary_max) from free text, or (None, None).

    Deterministic, regex-based, deliberately conservative: a match must carry
    a '$' or a 'k' suffix and survive plausibility bounds, so years of
    experience, percentages, 401(k) mentions, and headcounts never parse as
    salaries. Company-money figures — budgets, revenue/MRR/ARR, funding
    rounds, valuations, transaction volume — are rejected via same-clause
    context (:func:`_sal_context_ok`). Handles '$140k-$170k', '$140,000 to
    $170,000', '140-170k', 'between $X and $Y', hourly rates ('$45/hr',
    '$45 per hour' — annualized x2080), and 'up to $X' (max only).
    """
    if not text:
        return None, None
    # Cap the scan — salary lines live near the top or bottom of postings and
    # descriptions are already truncated by the scrapers.
    text = text[:6000]

    # Hourly range first, so '$40 - $50 per hour' isn't read as an annual range.
    for m in _SAL_HOURLY_RANGE_RE.finditer(text):
        d1, n1, k1, d2, n2, k2 = m.groups()
        if not (d1 or d2) or k1 or k2:
            continue
        lo, hi = _sal_value(n1, False), _sal_value(n2, False)
        if _SAL_HOURLY_MIN <= lo <= hi <= _SAL_HOURLY_MAX:
            return lo * _HOURS_PER_YEAR, hi * _HOURS_PER_YEAR

    # Annual ranges: 'between $X and $Y' plus the plain separator forms.
    for pattern in (_SAL_BETWEEN_RE, _SAL_RANGE_RE):
        for m in pattern.finditer(text):
            d1, n1, k1, d2, n2, k2 = m.groups()
            if not (d1 or d2 or k1 or k2):
                continue  # no $ and no k — years, page ranges, dates, ...
            if not _sal_context_ok(text, m.start(), m.end()):
                continue
            lo = _sal_value(n1, bool(k1), other_has_k=bool(k2))
            hi = _sal_value(n2, bool(k2), other_has_k=bool(k1))
            if _SAL_ANNUAL_MIN <= lo <= hi <= _SAL_ANNUAL_MAX:
                return lo, hi

    # Single hourly rate — the hourly marker itself is strong salary context.
    for m in _SAL_HOURLY_SINGLE_RE.finditer(text):
        _d, n, k = m.groups()
        if k:
            continue
        val = _sal_value(n, False)
        if _SAL_HOURLY_MIN <= val <= _SAL_HOURLY_MAX:
            annual = val * _HOURS_PER_YEAR
            if re.search(r"up\s+to\s*$", text[:m.start()], re.IGNORECASE):
                return None, annual
            return annual, None

    # 'up to $X' — max only.
    for m in _SAL_UP_TO_RE.finditer(text):
        d, n, k = m.groups()
        if not (d or k):
            continue
        if not _sal_context_ok(text, m.start(), m.end()):
            continue
        val = _sal_value(n, bool(k))
        if _SAL_ANNUAL_MIN <= val <= _SAL_ANNUAL_MAX:
            return None, val

    return None, None


def finalize_scraper_jobs(jobs: list[dict]) -> list[dict]:
    """Shared post-processing for scraper job dicts (mutates in place).

    Guarantees the cross-agent contract fields on every job:

    - ``date_confidence``: 'exact' | 'fuzzy' | 'missing'. Scraper-stamped
      values win; otherwise derived from ``date_posted`` (parseable date ->
      'exact', absent/unparseable -> 'missing').
    - ``salary_source``: 'reported' when the scraper provided structured
      salary, 'parsed_from_description' when :func:`extract_salary_range`
      recovers a range from the description (also fills salary_min/max),
      else None.
    - ``work_type_confidence``: 'reported' when the scraper carried a
      definitive remote flag (``remote_flag_reported``), else 'inferred'.
    """
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if "date_confidence" not in job:
            job["date_confidence"] = date_confidence_for(job.get("date_posted"))
        if job.get("salary_min") is not None or job.get("salary_max") is not None:
            if not job.get("salary_source"):
                job["salary_source"] = "reported"
        elif not job.get("salary_source"):
            if job.get("vertical") not in (None, "career"):
                # Quest rows carry only pay their source states outright. A
                # "$50 stipend" sentence in a study description must never
                # become a promised pay figure.
                job["salary_source"] = None
            else:
                lo, hi = extract_salary_range(job.get("description") or "")
                if lo is not None or hi is not None:
                    job["salary_min"] = lo
                    job["salary_max"] = hi
                    job["salary_source"] = "parsed_from_description"
                else:
                    job["salary_source"] = None
        if "work_type_confidence" not in job:
            job["work_type_confidence"] = (
                "reported" if job.get("remote_flag_reported") else "inferred"
            )
    return jobs


# Query params that only track where a click came from — never identity.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset({
    "ref", "refid", "ref_id", "referer", "referrer", "src", "source",
    "gh_src", "lever-source", "lever-origin", "ashby_jid_src",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
    "trackingid", "tracking_id", "trk", "campaign", "vq_campaign",
})

_GREENHOUSE_HOSTS = frozenset({
    "boards.greenhouse.io", "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io",
})
_LEVER_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})

_GH_JOB_PATH_RE = re.compile(r"^/([^/]+)/jobs/(\d+)")
_LEVER_JOB_PATH_RE = re.compile(r"^/([^/]+)/([0-9a-fA-F-]{36})")


def _is_tracking_param(name: str) -> bool:
    low = name.lower()
    return low in _TRACKING_PARAMS or low.startswith(_TRACKING_PARAM_PREFIXES)


def canonicalize_job_url(url: str | None) -> str:
    """Canonical dedup key for a job URL ('' when there is no URL).

    The same posting arrives from different boards with different tracking
    decorations (utm_*, ref, gh_src, lever-source) or URL shapes (Greenhouse
    boards. vs job-boards. hosts, the /embed/job_app?for=&token= form, Lever
    /apply suffixes), defeating exact-URL dedup. This strips tracking params
    and fragments, lowercases scheme/host, drops trailing slashes, and maps
    Greenhouse/Lever URLs onto their stable company+job-id form. Meaningful
    params (e.g. ``gh_jid`` on embedded career pages) are preserved. Never
    raises — unparseable input is returned trimmed so callers can still key
    on it.
    """
    if not url:
        return ""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = parts.netloc.lower()
    path = parts.path or ""
    query = parse_qsl(parts.query, keep_blank_values=True)

    if host in _GREENHOUSE_HOSTS or host == "greenhouse.io":
        m = _GH_JOB_PATH_RE.match(path)
        if m:
            return f"https://boards.greenhouse.io/{m[1].lower()}/jobs/{m[2]}"
        if path.rstrip("/").endswith("/job_app"):
            q = {k.lower(): v for k, v in query}
            company, token = q.get("for"), q.get("token")
            if company and token:
                return f"https://boards.greenhouse.io/{company.lower()}/jobs/{token}"

    if host in _LEVER_HOSTS:
        m = _LEVER_JOB_PATH_RE.match(path)
        if m:
            return f"https://jobs.lever.co/{m[1].lower()}/{m[2].lower()}"

    kept_query = [(k, v) for k, v in query if not _is_tracking_param(k)]
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((
        parts.scheme.lower(),
        host,
        path,
        urlencode(sorted(kept_query)),
        "",  # fragment never identifies a different job
    ))


def _strip_html(html: str) -> str:
    """Crude HTML tag stripper for description fields."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:3000]


_COMPANY_NAME_CORRECTIONS: dict[str, str] = {
    "Openai": "OpenAI",
    "Dbt Labs": "dbt Labs",
    "Mongodb": "MongoDB",
    "Linkedin": "LinkedIn",
    "Github": "GitHub",
    "Grammarly": "Grammarly",
    "Hashicorp": "HashiCorp",
    "Snowflake": "Snowflake",
    "Databricks": "Databricks",
    "Cloudflare": "Cloudflare",
}


_LOWERCASE_WORDS = {"and", "of", "the", "in", "at", "by", "for", "on", "to"}


def _clean_company_name(slug: str) -> str:
    """Convert a URL slug to a properly-cased company name.

    1. Strip numeric suffixes added by Lever for disambiguation (e.g. "notion-2")
    2. Replace hyphens with spaces
    3. Apply ``.title()`` for basic capitalisation, lowercasing conjunctions/prepositions
    4. Apply corrections dict for known companies
    """
    # Strip trailing numeric disambiguation suffix (e.g. "notion-2" -> "notion")
    cleaned = re.sub(r"-\d+$", "", slug)
    # Replace hyphens with spaces, then title-case
    words = cleaned.replace("-", " ").title().split()
    # Lowercase minor words (but never the first word)
    for i in range(1, len(words)):
        if words[i].lower() in _LOWERCASE_WORDS:
            words[i] = words[i].lower()
    name = " ".join(words)
    # Apply corrections for known companies
    return _COMPANY_NAME_CORRECTIONS.get(name, name)


# Well-known crypto/web3 employers that may arrive via watchlist or dynamic
# ATS discovery (i.e. not necessarily in the curated seed crypto sections).
# Jobs from any of these — or from a seed-file "Crypto / web3" section — get
# crypto-aware role matching so titles like "Smart Contract Engineer" survive
# even when they don't word-match the user's target roles.
_CRYPTO_COMPANY_BASE: frozenset[str] = frozenset({
    "alchemy", "magiceden", "phantom", "coinbase", "kraken", "circle",
    "consensys", "chainalysis", "anchorage", "fireblocks", "uniswap",
    "opensea", "ledger", "0x", "paradigm", "ripple", "polygon", "aptoslabs",
    "matterlabs", "offchainlabs", "blockchaincom", "gemini", "dydx",
})


def _norm_company_key(value: str | None) -> str:
    """Normalize a slug or display name to a comparable key (alnum, lowercase).

    ``magiceden`` and ``Magic Eden`` both normalize to ``magiceden`` so a job's
    cleaned company name matches the crypto slug it came from.
    """
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def crypto_company_slugs() -> set[str]:
    """Curated crypto/web3 company slugs (seed crypto sections + base set)."""
    slugs: set[str] = set(_CRYPTO_COMPANY_BASE)
    for seed_file in ("ashby_seed.txt", "greenhouse_seed.txt", "lever_seed.txt"):
        slugs.update(s.lower() for s in _load_seed_section(seed_file, "crypto"))
    return slugs


# Computed once at import — small, read-only.
_CRYPTO_COMPANY_KEYS: frozenset[str] = frozenset(
    _norm_company_key(s) for s in crypto_company_slugs()
)


def is_crypto_company(name_or_slug: str | None) -> bool:
    """True if a company slug or display name is a known crypto/web3 employer."""
    key = _norm_company_key(name_or_slug)
    return bool(key) and key in _CRYPTO_COMPANY_KEYS


# Founding-role aliases bypass the role-matching gate by default.
# These titles ("Founding Engineer", "Member of Technical Staff") rarely
# word-overlap with a user's normal target roles, so strict matching drops
# them. They're high-signal startup roles that almost any "want a startup
# job" user wants to see — global default per design.
_FOUNDING_TITLE_PATTERNS: tuple[str, ...] = (
    "founding engineer",
    "founding designer",
    "founding pm",
    "founding product manager",
    "founding product",
    "founding software",
    "founding member",
    "founding team",
    "member of technical staff",
    "member of the technical staff",
    "early engineer",
    "first engineer",
    "first engineering hire",
    "first product hire",
    "first design hire",
)
# Standalone tokens (matched as whole words). "mts" is a common shorthand at
# AI labs but we don't want to match it inside other words.
_FOUNDING_TOKEN_PATTERNS: tuple[str, ...] = ("mts",)


def _is_founding_title(title_lower: str, title_words: set[str]) -> bool:
    """True if the (lowercased) title looks like a founding/early-hire role."""
    if any(p in title_lower for p in _FOUNDING_TITLE_PATTERNS):
        return True
    return any(t in title_words for t in _FOUNDING_TOKEN_PATTERNS)


# Articles / conjunctions / prepositions — true noise, dropped before any
# word-level comparison.
_NOISE: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "&",
})

# Generic, DOMAIN-AGNOSTIC title words: seniority levels, role-type words, and
# structural fillers that appear across virtually every profession. A title
# matching a role on ONLY these words is meaningless ("Marketing Manager" vs
# "Nurse Manager" both have "manager"), so domain-aware matching ignores them
# and keys on a role's remaining *domain* words instead.
_GENERIC_TITLE_WORDS: frozenset[str] = frozenset({
    # seniority
    "senior", "sr", "jr", "junior", "mid", "staff", "principal", "lead",
    "leads", "head", "vp", "svp", "evp", "chief", "director", "manager",
    "mgr", "associate", "intern", "fellow", "distinguished", "executive",
    # role-type
    "engineer", "engineering", "developer", "dev", "technician", "consultant",
    "consulting", "specialist", "coordinator", "administrator", "analyst",
    "architect", "sme", "expert", "professional", "contractor", "contract",
    # roman-numeral / ordinal level markers
    "i", "ii", "iii", "iv", "v",
    # structural fillers
    "role", "position", "team", "full", "time", "fulltime", "part",
    "remote", "hybrid", "onsite", "new", "grad", "of",
})

# Words ignored when deriving a role's domain signature.
_NON_DOMAIN_WORDS: frozenset[str] = _NOISE | _GENERIC_TITLE_WORDS

# Distinct job-FAMILY signal words. A title carrying one of these almost always
# belongs to a different occupation than a data/eng/infra role, even when it
# shares a single generic domain word ("data", "analytics", "ai platform"):
#   - "Lead Data Center/Hyperscale Sales Development"  -> a SALES role
#   - "Senior Product Designer, AI Platform"           -> a DESIGNER
#   - "Finance Analytics Manager (Product & Eng)"      -> a FINANCE function
# The guard built on this set is SELF-ADJUSTING (see ``_match_roles``): any word
# that appears in the user's own ``roles`` is removed from the effective set, so
# a sales/marketing/design user is never penalised for their own family.
#
# Kept deliberately TIGHT — broad, cross-functional words that legitimately
# appear in data/platform titles (revenue, governance, compliance, identity,
# analytics, data, platform, infrastructure, financial, product, engineering)
# are intentionally EXCLUDED. Note "finance" (not "financial"): plural folding
# keeps them distinct so "Financial Infrastructure" is not treated as finance.
_OFF_FAMILY_WORDS: frozenset[str] = frozenset({
    "sales", "seller", "designer", "design", "marketing", "merchandising",
    "recruiter", "recruiting", "sourcer", "security", "cyber", "finance",
})

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize_word(word: str) -> str:
    """Light plural folding: strip a single trailing 's' (len>3) for tolerance.

    Lets "platforms" match "platform" and keeps "analytics"/"analytic" aligned.
    The length guard avoids mangling short tokens (e.g. "is", "os") and the
    roman-numeral/level markers, where a trailing 's' carries meaning.
    """
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _domain_words(words: set[str]) -> set[str]:
    """A role's domain signature: its words minus generic + noise words,
    plural-normalized. e.g. "Head of Data Platform" -> {data, platform}."""
    return {
        _normalize_word(w) for w in words if w not in _NON_DOMAIN_WORDS
    }


def _is_off_family_title(norm_title_words: set[str], roles: list[str]) -> bool:
    """True if the title belongs to a different job family than the user's roles.

    The off-family set (:data:`_OFF_FAMILY_WORDS`) is made SELF-ADJUSTING by
    removing any word the user's own ``roles`` use (plural-normalized), so a
    sales/marketing/design user is never penalised for their own family. All
    comparisons are plural-normalized so "sales"->"sale" still matches a title's
    "sale", while "finance" stays distinct from "financial".

    ``norm_title_words`` must already be the plural-normalized set of the
    title's words (as produced for domain matching in :func:`_match_roles`).
    """
    role_words: set[str] = set()
    for r in roles:
        role_words.update(_normalize_word(w) for w in _WORD_RE.findall(r.lower()))
    effective_off_family = {
        _normalize_word(w) for w in _OFF_FAMILY_WORDS
        if _normalize_word(w) not in role_words
    }
    return bool(effective_off_family & norm_title_words)


def _match_roles(
    title: str,
    roles: list[str] | None,
    *,
    include_founding: bool = True,
    match_mode: str = "all_significant",
) -> bool:
    """Check if a job title matches any of the target roles (domain-aware).

    Matching keys on each role's *domain* words — its significant words minus
    generic seniority/role-type/filler words (:data:`_GENERIC_TITLE_WORDS`) and
    noise. So "Head of Data Platform" carries domain {data, platform}; an
    off-domain title that only shares a generic word ("Service Desk Manager")
    never matches. Words are plural-normalized so "Platforms" matches "Platform".

    ``match_mode`` controls the matching strategy:

    - ``"exact"``     — substring tier only. Strictest. "data engineer" must
                        appear contiguously in the title.
    - ``"all_significant"`` (default) — substring OR a role has ≥1 domain word
                        and ALL of its domain words appear in the title (any
                        order). "Senior Data Platform Engineer" matches role
                        "Head of Data Platform" via domain {data, platform}.
    - ``"any_word"``  — substring OR role and title share at least one *domain*
                        word. Wide net within the domain for the ``loose``
                        preset / balanced place-bound rescue. A shared generic
                        word ("engineer", "manager") is NOT enough.

    Founding-role bypass — "Founding Engineer", "Member of Technical Staff",
    "MTS", etc. always pass when ``include_founding=True``. These titles
    rarely word-overlap with normal target roles, but they're high-signal
    startup positions users almost always want to see.

    A role whose domain-word set is empty after stripping (e.g. "engineering
    manager", "senior engineer") falls back to the significant-word subset
    rule: ALL of its non-noise words must appear in the title, so "Manager of
    Engineering" matches "engineering manager" but a single shared generic
    word ("manager" alone) never does.

    Off-family guard — a title carrying a distinct job-family word
    (:data:`_OFF_FAMILY_WORDS`: sales / designer / marketing / security /
    finance / …) is rejected as a different occupation, *even if* it shares a
    domain word like "data" or "analytics". The guard is self-adjusting: any
    off-family word that appears in the user's own ``roles`` is dropped from the
    effective set, so e.g. a sales user is never penalised for sales titles. An
    explicit full-role substring match (the tier below) still wins over the
    guard.

    Returns False if no role matches under the chosen mode.
    """
    if not roles:
        return True
    title_lower = title.lower()
    raw_title_words = set(_WORD_RE.findall(title_lower))
    if include_founding and _is_founding_title(title_lower, raw_title_words):
        return True
    # Plural-normalized title words for domain comparison.
    norm_title_words = {_normalize_word(w) for w in raw_title_words}

    # Exact substring tier FIRST: an explicit full-role match always wins, even
    # over the off-family guard below.
    for r in roles:
        if r.lower() in title_lower:
            return True

    # Off-family guard: a title from a different job family (e.g. a sales or
    # designer role that merely shares the word "data") is rejected here, after
    # the exact-substring tier but before domain matching.
    if _is_off_family_title(norm_title_words, roles):
        return False

    for r in roles:
        role_lower = r.lower()
        if match_mode == "exact":
            continue
        role_words = set(_WORD_RE.findall(role_lower))
        role_domain = _domain_words(role_words)
        if not role_domain:
            # Purely-generic role ("engineering manager", "senior engineer"):
            # no domain signature to key on. Fall back to the significant-word
            # subset rule (words minus noise) so non-contiguous forms like
            # "Manager of Engineering" still match — a single shared generic
            # word is still not enough.
            significant = {
                _normalize_word(w) for w in role_words if w not in _NOISE
            }
            if significant and significant.issubset(norm_title_words):
                return True
            continue
        if match_mode == "any_word":
            if role_domain & norm_title_words:
                return True
        else:  # "all_significant" (default)
            if role_domain.issubset(norm_title_words):
                return True
    return False


# High-precision crypto/web3 signals — matched as substrings. These rarely
# appear in non-crypto job titles, so substring matching is safe.
_CRYPTO_SUBSTRING_TERMS: tuple[str, ...] = (
    "blockchain", "web3", "web 3", "solidity", "smart contract", "defi",
    "crypto", "evm", "zero knowledge", "zero-knowledge", "ethereum", "solana",
    "bitcoin", "nft", "dao", "dapp", "tokenomics", "stablecoin", "onchain",
    "on-chain", "staking", "validator", "layer 2", "rollup", "zksync",
)
# Crypto-leaning but ambiguous terms — matched as whole words only so we don't
# fire on unrelated substrings. The broadest offenders ('rust', 'node') are
# intentionally omitted: they tag far more non-crypto roles than crypto ones.
_CRYPTO_WORD_TERMS: tuple[str, ...] = (
    "protocol", "token", "consensus", "zk", "l2", "wallet",
)


def _has_crypto_terms(text: str | None) -> bool:
    """True if ``text`` carries a crypto/web3/blockchain signal."""
    if not text:
        return False
    low = text.lower()
    if any(term in low for term in _CRYPTO_SUBSTRING_TERMS):
        return True
    words = set(re.findall(r"[a-z0-9]+", low))
    return any(term in words for term in _CRYPTO_WORD_TERMS)


def _match_roles_crypto(
    title: str,
    roles: list[str] | None,
    *,
    include_founding: bool = True,
    match_mode: str = "all_significant",
) -> bool:
    """Role matching that also passes crypto/web3 roles.

    After the normal role match, a job whose *title* carries a crypto signal
    passes even when the title doesn't word-match the target roles. Used only
    for jobs from crypto-domain sources/companies so non-crypto searches don't
    pick up cross-domain noise. Matching is title-only on purpose: board/tag
    metadata (e.g. cryptojobslist's category tags) is too noisy — it would let
    every listing through and turn role filtering into a no-op.

    The crypto rescue is scoped to eng/data/infra breadth, NOT sales/design:
    the off-family guard still applies, so a crypto SALES or DESIGNER title
    ("Blockchain Sales Rep", "Web3 Product Designer") is rejected even though
    it carries a crypto signal. Genuine crypto eng/data roles ("Solidity
    Engineer", "Crypto Data Engineer") are unaffected.
    """
    if _match_roles(
        title,
        roles,
        include_founding=include_founding,
        match_mode=match_mode,
    ):
        return True
    if not _has_crypto_terms(title):
        return False
    # Crypto rescue, but never into a different job family (sales/design/etc.).
    if roles:
        norm_title_words = {
            _normalize_word(w) for w in _WORD_RE.findall(title.lower())
        }
        if _is_off_family_title(norm_title_words, roles):
            return False
    return True


# ATS scrapers emit a clean, slug-derived company name and set the ``crypto``
# flag from the authoritative slug. Other sources (JobSpy boards, remote-job
# firehoses) carry arbitrary free-text company names, so we must NOT infer
# crypto-domain from those — a non-crypto employer that happens to be named
# "Polygon"/"Circle"/"Gemini" would otherwise get crypto-rescued and leak
# off-role crypto-titled jobs into a generic search.
_ATS_SOURCES: frozenset[str] = frozenset({"ashby", "greenhouse", "lever", "workday"})


def job_is_crypto_domain(job: dict) -> bool:
    """True if a job dict belongs to a crypto/web3 source or company.

    Used to decide whether crypto-aware role matching applies. The criteria
    are deliberately source/company-scoped (not title-based) so a generic
    search doesn't get crypto results mixed in.
    """
    source = (job.get("source") or "").lower()
    if source == "cryptojobslist":
        return True
    if job.get("crypto"):
        return True
    # Company-name fallback only for ATS sources, where ``company`` is a curated
    # slug-derived name. This lets the DB purge — which can't see the in-memory
    # ``crypto`` flag — still treat persisted ATS crypto-company records as
    # crypto-domain, without crypto-tagging a JobSpy namesake company.
    if source in _ATS_SOURCES:
        return is_crypto_company(job.get("company"))
    return False


def job_passes_role_filter(
    job: dict,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    strictness: str = "balanced",
    allow_crypto_rescue: bool = True,
) -> bool:
    """Single source of truth for "does this job survive the role filter".

    Shared by the in-memory pipeline filter and the DB record purge so the two
    can never disagree (the purge previously used a stricter matcher and
    deleted crypto/founding/place jobs the pipeline kept). Applies:
      - the balanced non-remote ``any_word`` rescue (place-bound jobs),
      - crypto-aware matching for crypto-domain jobs in non-strict modes.
    """
    title = job.get("title", "") or ""
    mode = match_mode
    if strictness == "balanced" and match_mode == "all_significant" and not job.get("is_remote"):
        mode = "any_word"
    if allow_crypto_rescue and strictness != "strict" and job_is_crypto_domain(job):
        return _match_roles_crypto(
            title, roles,
            match_mode=mode, include_founding=include_founding,
        )
    return _match_roles(
        title, roles, match_mode=mode, include_founding=include_founding,
    )
