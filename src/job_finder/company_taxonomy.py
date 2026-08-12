"""Persistent, source-independent company and job taxonomy.

Source names answer *where Questboard found a posting*.  They do not answer
what industry the employer belongs to: an Alchemy opening fetched directly
from Ashby is still a crypto job.  This module keeps those concepts separate.

Every observed career row receives deterministic ``industry_tags`` and
``ecosystem_tags``.  A small JSON catalog remembers company identity, tags,
and official ATS boards learned from portfolio boards and aggregators.  The
catalog is deliberately local and model-free; it grows from source evidence
and remains useful on the next refresh even when discovery services are down.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_PACKAGE_CACHE_DIR = Path(__file__).parent / "tools" / "scrapers" / "data" / "cache"
# Desktop bundles are replaced on upgrade, so learned company identity must
# live beside the user's database rather than inside the packaged sidecar.
_RUNTIME_DATA_DIR = os.environ.get("JOB_FINDER_DATA_DIR") or os.environ.get("DATA_DIR")
_CACHE_PATH = (
    Path(_RUNTIME_DATA_DIR) / "cache" / "company_catalog.json"
    if _RUNTIME_DATA_DIR
    else _PACKAGE_CACHE_DIR / "company_catalog.json"
)
_CATALOG_VERSION = 2
_CATALOG_LOCK = threading.RLock()
_CATALOG_CACHE: dict[str, Any] | None = None
_CATALOG_CACHE_PATH: str = ""
_CATALOG_CACHE_MTIME_NS: int = -1

# These sources are crypto universes by construction.  A source observation
# is authoritative enough to classify the company without guessing from a
# generic company name such as Circle or Flow.
CRYPTO_SOURCES: frozenset[str] = frozenset({
    "cryptojobslist",
    "web3career",
    "getro",
    "consider",
})

# High-confidence bootstrap identities.  The persistent catalog quickly grows
# beyond this list from ecosystem feeds.  Keep the set conservative because
# some crypto brands (Circle, Flow, Gemini) collide with ordinary companies.
_CRYPTO_COMPANY_KEYS: frozenset[str] = frozenset({
    "0x",
    "alchemy",
    "anchorage",
    "anchoragedigital",
    "aptoslabs",
    "arbitrum",
    "anza",
    "blockchaincom",
    "blockworks",
    "chainalysis",
    "coinbase",
    "consensys",
    "dydx",
    "dourolabs",
    "eigenlabs",
    "fireblocks",
    "flipside",
    "flipsidecrypto",
    "fomofamily",
    "galaxy",
    "galaxydigital",
    "helius",
    "jito",
    "kraken",
    "layerzero",
    "ledger",
    "lightspark",
    "magiceden",
    "matterlabs",
    "mystenlabs",
    "offchainlabs",
    "ondofinance",
    "opensea",
    "paradigm",
    "phantom",
    "polygonlabs",
    "pumpfun",
    "ripple",
    "solanafoundation",
    "solflare",
    "uniswaplabs",
    "wormhole",
})

_CRYPTO_SIGNALS: tuple[str, ...] = (
    "blockchain",
    "web3",
    "web 3",
    "crypto",
    "decentralized finance",
    "defi",
    "onchain",
    "on-chain",
    "smart contract",
    "digital asset",
    "stablecoin",
    "tokenization",
    "token protocol",
    "wallet infrastructure",
    "validator network",
)

# Ecosystem tags are additive: a role can be both Ethereum and Base, or both
# Solana and a broader crypto role.  Patterns use word boundaries wherever a
# short/common term would otherwise over-match prose.
_ECOSYSTEM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "solana": (re.compile(r"\bsolana\b", re.I),),
    "ethereum": (re.compile(r"\bethereum\b", re.I), re.compile(r"\bevm\b", re.I)),
    "bitcoin": (re.compile(r"\bbitcoin\b", re.I), re.compile(r"\blightning network\b", re.I)),
    "base": (re.compile(r"\bbase (?:chain|network|ecosystem)\b", re.I),),
    "arbitrum": (re.compile(r"\barbitrum\b", re.I),),
    "optimism": (
        re.compile(r"\boptimism (?:network|ecosystem|collective|foundation|protocol|blockchain)\b", re.I),
        re.compile(r"\bop stack\b", re.I),
    ),
    "polygon": (re.compile(r"\bpolygon (?:labs|pos|zk|network|ecosystem)\b", re.I),),
    "aptos": (re.compile(r"\baptos\b", re.I),),
    "sui": (re.compile(r"\bsui (?:network|ecosystem|move|blockchain)\b", re.I),),
    "cosmos": (
        re.compile(r"\bcosmos (?:sdk|hub|ecosystem|network|blockchain)\b", re.I),
        re.compile(r"\binter[- ]blockchain communication\b", re.I),
    ),
    "near": (re.compile(r"\bnear protocol\b", re.I),),
    "avalanche": (
        re.compile(r"\bavalanche (?:c-chain|network|ecosystem|blockchain|protocol)\b", re.I),
        re.compile(r"\bavax\b", re.I),
    ),
    "polkadot": (re.compile(r"\bpolkadot\b", re.I),),
}


def normalize_company_key(value: str | None) -> str:
    """Normalize display names and ATS slugs to a stable catalog key."""
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _normalize_tags(value: object) -> set[str]:
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("["):
            try:
                value = json.loads(raw)
            except (TypeError, ValueError):
                value = [raw]
        elif raw:
            value = [raw]
        else:
            value = []
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {
        str(tag).strip().casefold()
        for tag in value
        if str(tag).strip()
    }


def tags_json(value: object) -> str:
    """Serialize a tag collection in a stable format for SQLite text fields."""
    return json.dumps(sorted(_normalize_tags(value)), separators=(",", ":"))


def parse_tags(value: object) -> list[str]:
    """Return a normalized list from either an in-memory list or stored JSON."""
    return sorted(_normalize_tags(value))


def _empty_catalog() -> dict[str, Any]:
    return {
        "version": _CATALOG_VERSION,
        "updated_at": "",
        "companies": {},
    }


def _load_catalog() -> dict[str, Any]:
    global _CATALOG_CACHE, _CATALOG_CACHE_PATH, _CATALOG_CACHE_MTIME_NS

    with _CATALOG_LOCK:
        cache_path = str(_CACHE_PATH)
        try:
            mtime_ns = _CACHE_PATH.stat().st_mtime_ns
        except OSError:
            mtime_ns = -1
        if (
            _CATALOG_CACHE is not None
            and _CATALOG_CACHE_PATH == cache_path
            and _CATALOG_CACHE_MTIME_NS == mtime_ns
        ):
            return _CATALOG_CACHE
        try:
            payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            payload = _empty_catalog()
        if not isinstance(payload, dict) or not isinstance(payload.get("companies"), dict):
            payload = _empty_catalog()
        _CATALOG_CACHE = payload
        _CATALOG_CACHE_PATH = cache_path
        _CATALOG_CACHE_MTIME_NS = mtime_ns
        return payload


def _save_catalog(payload: dict[str, Any]) -> None:
    global _CATALOG_CACHE, _CATALOG_CACHE_PATH, _CATALOG_CACHE_MTIME_NS

    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["version"] = _CATALOG_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=_CACHE_PATH.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(_CACHE_PATH)
    try:
        mtime_ns = _CACHE_PATH.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    _CATALOG_CACHE = payload
    _CATALOG_CACHE_PATH = str(_CACHE_PATH)
    _CATALOG_CACHE_MTIME_NS = mtime_ns


def _catalog_entry(company: str | None) -> dict[str, Any] | None:
    key = normalize_company_key(company)
    if not key:
        return None
    entry = (_load_catalog().get("companies") or {}).get(key)
    return entry if isinstance(entry, dict) else None


def is_known_crypto_company(company: str | None) -> bool:
    """Return true for a bootstrapped or source-confirmed crypto employer."""
    key = normalize_company_key(company)
    if not key:
        return False
    if key in _CRYPTO_COMPANY_KEYS:
        return True
    entry = _catalog_entry(company)
    if not entry:
        return False
    return "crypto" in _normalize_tags(entry.get("company_industry_tags"))


def _ecosystems_in(text: str) -> set[str]:
    return {
        ecosystem
        for ecosystem, patterns in _ECOSYSTEM_PATTERNS.items()
        if any(pattern.search(text) for pattern in patterns)
    }


def classify_job_taxonomy(
    *,
    company: str | None,
    source: str | None,
    title: str | None = None,
    description: str | None = None,
    crypto: bool = False,
    industry_tags: object = None,
    ecosystem_tags: object = None,
) -> tuple[list[str], list[str]]:
    """Classify one row without relying on its UI source category.

    Explicit source/job metadata and a previously confirmed company identity
    win.  Generic-source prose requires two independent crypto signals (or a
    named chain) before it can classify an otherwise unknown company, which
    keeps casual mentions from polluting the Crypto shelf.
    """
    industries = _normalize_tags(industry_tags)
    ecosystems = _normalize_tags(ecosystem_tags)
    source_key = (source or "").strip().casefold()
    combined = " ".join((title or "", description or ""))
    ecosystems.update(_ecosystems_in(combined))

    entry = _catalog_entry(company)
    if entry:
        industries.update(_normalize_tags(entry.get("company_industry_tags")))
        ecosystems.update(_normalize_tags(entry.get("company_ecosystem_tags")))

    low = combined.casefold()
    # Boundaries matter for short terms: ``defi`` must not match ``define``.
    signal_count = sum(
        1
        for signal in _CRYPTO_SIGNALS
        if re.search(rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])", low)
    )
    crypto_confirmed = (
        crypto
        or source_key in CRYPTO_SOURCES
        or is_known_crypto_company(company)
        or bool(ecosystems)
        or signal_count >= 2
    )
    if crypto_confirmed:
        industries.add("crypto")
    return sorted(industries), sorted(ecosystems)


def _extract_ats_boards(url: str | None) -> dict[str, set[str]]:
    if not url:
        return {}
    from job_finder.tools.scrapers._ats_discovery import ATS_HOSTS, extract_slug

    found: dict[str, set[str]] = {}
    for host in ATS_HOSTS:
        slug = extract_slug(host, url)
        if slug:
            found.setdefault(host, set()).add(slug)
    return found


def observe_jobs(jobs: Iterable[dict], *, source_category: str | None = None) -> int:
    """Tag jobs, grow the company catalog, and promote official ATS boards.

    Called once at the common scraper boundary, so every aggregator and
    portfolio source contributes discovery evidence without bespoke glue.
    Returns the number of catalog companies changed.
    """
    rows = [job for job in jobs if isinstance(job, dict)]
    if not rows:
        return 0

    changed_keys: set[str] = set()
    promotions: dict[str, set[str]] = {}
    now = datetime.now(timezone.utc).isoformat()

    with _CATALOG_LOCK:
        payload = _load_catalog()
        companies = payload.setdefault("companies", {})
        if not isinstance(companies, dict):
            companies = {}
            payload["companies"] = companies

        for job in rows:
            company = str(job.get("company") or "").strip()
            source = str(job.get("source") or "").strip().casefold()
            source_is_crypto = source_category == "crypto" or source in CRYPTO_SOURCES
            company_is_crypto = (
                bool(job.get("company_crypto"))
                or normalize_company_key(company) in _CRYPTO_COMPANY_KEYS
            )
            industries, ecosystems = classify_job_taxonomy(
                company=company,
                source=source,
                title=str(job.get("title") or job.get("job_title") or ""),
                description=str(job.get("description") or ""),
                crypto=bool(job.get("crypto")) or source_is_crypto,
                industry_tags=job.get("industry_tags"),
                ecosystem_tags=job.get("ecosystem_tags"),
            )
            job["industry_tags"] = industries
            job["ecosystem_tags"] = ecosystems
            if "crypto" in industries:
                job["crypto"] = True

            key = normalize_company_key(company)
            boards: dict[str, set[str]] = {}
            for candidate_url in (
                job.get("url"),
                job.get("job_url"),
                job.get("direct_application_url"),
            ):
                for host, slugs in _extract_ats_boards(str(candidate_url or "")).items():
                    boards.setdefault(host, set()).update(slugs)
            for host, slugs in boards.items():
                promotions.setdefault(host, set()).update(slugs)
            if not key:
                continue

            old = companies.get(key)
            entry = dict(old) if isinstance(old, dict) else {}
            previous = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            entry["name"] = company or entry.get("name") or key
            # Persist only company-level evidence. Job-level crypto evidence
            # remains on that row and must not contaminate unrelated openings
            # from the same general employer on LinkedIn or an ATS.
            prior_company_industries = _normalize_tags(entry.get("company_industry_tags"))
            prior_company_ecosystems = _normalize_tags(entry.get("company_ecosystem_tags"))
            if company_is_crypto:
                prior_company_industries.add("crypto")
                prior_company_ecosystems.update(ecosystems)
            entry["company_industry_tags"] = sorted(prior_company_industries)
            entry["company_ecosystem_tags"] = sorted(prior_company_ecosystems)
            # Remove v1 fields, which mixed job evidence with company identity.
            entry.pop("industry_tags", None)
            entry.pop("ecosystem_tags", None)
            entry["sources"] = sorted(
                _normalize_tags(entry.get("sources")) | ({source} if source else set())
            )
            existing_boards = entry.get("ats_boards")
            if not isinstance(existing_boards, dict):
                existing_boards = {}
            for host, slugs in boards.items():
                existing_boards[host] = sorted(
                    set(existing_boards.get(host) or []) | slugs
                )
            entry["ats_boards"] = existing_boards
            entry.setdefault("first_seen_at", now)
            entry["last_seen_at"] = now
            companies[key] = entry
            current = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            if current != previous:
                changed_keys.add(key)

        if changed_keys:
            try:
                _save_catalog(payload)
            except OSError as exc:
                logger.warning("Company taxonomy catalog could not be saved: %s", exc)

    if promotions:
        try:
            from job_finder.tools.scrapers._ats_discovery import promote_slugs

            for host, slugs in promotions.items():
                promote_slugs(host, slugs)
        except Exception as exc:
            logger.warning("ATS URL promotion failed (non-fatal): %s", exc)
    return len(changed_keys)
