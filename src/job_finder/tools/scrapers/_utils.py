"""Shared helpers for scraper modules."""

from __future__ import annotations

import logging
import re
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


def _match_roles(
    title: str,
    roles: list[str] | None,
    *,
    include_founding: bool = True,
    match_mode: str = "all_significant",
) -> bool:
    """Check if a job title matches any of the target roles.

    ``match_mode`` controls the matching strategy:

    - ``"exact"``     — substring tier only. Strictest. "data engineer" must
                        appear contiguously in the title.
    - ``"all_significant"`` (default) — substring OR every significant role
                        word appears in the title (any order). "Platform
                        Engineer, Data" matches role "data platform engineer".
    - ``"any_word"``  — substring OR any single significant role word appears
                        in the title. Wide net for the ``loose`` strictness
                        preset. "Senior Coordinator" matches "Marketing
                        Coordinator" because both share "coordinator".

    Founding-role bypass — "Founding Engineer", "Member of Technical Staff",
    "MTS", etc. always pass when ``include_founding=True``. These titles
    rarely word-overlap with normal target roles, but they're high-signal
    startup positions users almost always want to see.

    Returns False if no role matches under the chosen mode.
    """
    if not roles:
        return True
    title_lower = title.lower()
    # Noise words to ignore during word-level matching
    _NOISE = {"a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "&"}
    # Strip punctuation for word-level matching
    title_words = set(re.findall(r"[a-z0-9]+", title_lower))
    if include_founding and _is_founding_title(title_lower, title_words):
        return True
    for r in roles:
        role_lower = r.lower()
        # Exact substring tier — fires in every mode
        if role_lower in title_lower:
            return True
        if match_mode == "exact":
            continue
        role_words = set(re.findall(r"[a-z0-9]+", role_lower)) - _NOISE
        if not role_words:
            continue
        if match_mode == "any_word":
            if role_words & title_words:
                return True
        else:  # "all_significant" (default)
            if role_words.issubset(title_words):
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
    """
    if _match_roles(
        title,
        roles,
        include_founding=include_founding,
        match_mode=match_mode,
    ):
        return True
    return _has_crypto_terms(title)


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
    if strictness != "strict" and job_is_crypto_domain(job):
        return _match_roles_crypto(
            title, roles,
            match_mode=mode, include_founding=include_founding,
        )
    return _match_roles(
        title, roles, match_mode=mode, include_founding=include_founding,
    )
