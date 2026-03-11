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


def _get_json(url: str, params: dict | None = None) -> dict | list | None:
    """GET a JSON endpoint with error handling."""
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
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


def _match_roles(title: str, roles: list[str] | None) -> bool:
    """Check if a job title matches any of the target roles (fuzzy).

    When *roles* are provided, each is checked as a substring of the title.
    If none match, a broad fallback catches common professional keywords
    across ALL industries (not just engineering) so no profession is excluded.
    """
    if not roles:
        return True
    title_lower = title.lower()
    for r in roles:
        if r.lower() in title_lower:
            return True
    # Broad fallback — universal professional keywords across all industries.
    # These cover seniority markers and generic role words, not domain-specific
    # terms, so a nurse, marketer, designer, or salesperson won't be filtered out.
    broad = [
        # Seniority / level markers (universal)
        "senior", "staff", "principal", "lead", "junior", "associate",
        "director", "head of", "vp ", "chief ", "founding",
        "manager", "supervisor", "coordinator",
        # Generic role words (cross-industry)
        "engineer", "analyst", "specialist", "consultant", "architect",
        "designer", "developer", "scientist", "researcher", "strategist",
        "advisor", "administrator", "operator", "planner", "producer",
        # Domain-neutral skill areas
        "data", "platform", "operations", "product", "project",
        "machine learning", "ml ", "ai ",
    ]
    return any(kw in title_lower for kw in broad)


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
