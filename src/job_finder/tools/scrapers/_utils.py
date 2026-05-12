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
) -> dict | list | None:
    """GET a JSON endpoint with error handling."""
    quiet_statuses = quiet_statuses or set()
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
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


def _match_roles_crypto(
    title: str,
    roles: list[str] | None,
    *,
    include_founding: bool = True,
    match_mode: str = "all_significant",
) -> bool:
    """Extended role matching that includes crypto/web3/blockchain terms."""
    if _match_roles(
        title,
        roles,
        include_founding=include_founding,
        match_mode=match_mode,
    ):
        return True
    title_lower = title.lower()
    crypto_terms = [
        "blockchain", "web3", "solidity", "smart contract", "defi",
        "crypto", "token", "protocol", "rust", "consensus",
        "zk", "zero knowledge", "evm", "l2", "layer 2",
    ]
    return any(kw in title_lower for kw in crypto_terms)
