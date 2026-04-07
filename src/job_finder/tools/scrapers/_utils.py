"""Shared helpers for scraper modules."""

from __future__ import annotations

import logging
import re
from html import unescape

import requests

logger = logging.getLogger(__name__)

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


def _match_roles(title: str, roles: list[str] | None) -> bool:
    """Check if a job title matches any of the target roles.

    Matching strategy (in order):
    1. Exact substring — "data engineer" in "Senior Data Engineer" ✓
    2. Word overlap  — all significant words of the role appear in the title
       (any order), so "Platform Engineer, Data" matches role "data platform engineer"

    Returns False if none match — no broad fallback so that role filtering
    stays precise to the user's profile.
    """
    if not roles:
        return True
    title_lower = title.lower()
    # Noise words to ignore during word-overlap matching
    _NOISE = {"a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "&"}
    # Strip punctuation for word-level matching
    import re as _re
    title_words = set(_re.findall(r"[a-z0-9]+", title_lower))
    for r in roles:
        role_lower = r.lower()
        # Fast path: exact substring
        if role_lower in title_lower:
            return True
        # Word overlap: all meaningful role words present in title (any order)
        role_words = set(_re.findall(r"[a-z0-9]+", role_lower)) - _NOISE
        if role_words and role_words.issubset(title_words):
            return True
    return False


def _match_roles_crypto(title: str, roles: list[str] | None) -> bool:
    """Extended role matching that includes crypto/web3/blockchain terms."""
    if _match_roles(title, roles):
        return True
    title_lower = title.lower()
    crypto_terms = [
        "blockchain", "web3", "solidity", "smart contract", "defi",
        "crypto", "token", "protocol", "rust", "consensus",
        "zk", "zero knowledge", "evm", "l2", "layer 2",
    ]
    return any(kw in title_lower for kw in crypto_terms)
