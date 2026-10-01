"""Funding and industry signals read from a posting's own text.

Scrapers never fill funding_stage or total_funding, so classify_company
tiered 391 of the 464 rows on the Oct 1 2026 board "Unknown" while 15 of
those postings state their round in the description ("we raised an
additional $100M in Series C financing"). The patterns here are strict and
anchored: a Series letter, a seed or pre-seed round, a Y Combinator mention,
a venture-backed phrase, unicorn status, an IPO, and a dollar amount sitting
directly on raised/backed-by/funding/Series wording. "Startups" in "from
startups to enterprises" is deliberately not a signal, nor is "digital
asset management", a valuation, "$50 million per round" (missiles), or a
client's raise ("Our clients have raised over $5B").

This is the one home for these heuristics. Each rule is pinned by the real
sentence that motivated it in tests/test_company_signals_from_posting_text.py.
"""

from __future__ import annotations

import re
from typing import Any

# A match preceded by client/customer talk is about someone else's company.
_ABOUT_OTHERS = re.compile(
    r"\bclients?\b|\bcustomers (?:have|who)\b|\bportfolio compan"
    r"|\bwe (?:help|serve|back|fund|invest in|work with|partner with)\b",
    re.I,
)
# A ticker right after "investment from X" or "backed by X" is the investor's.
_PUBLIC_OTHERS = re.compile(
    _ABOUT_OTHERS.pattern
    + r"|\b(?:investment from|backed by|funded by|investors? (?:include|like|such as))\b",
    re.I,
)
_LOOKBACK = 60

_PUBLIC = re.compile(
    r"\b(?:did|completed|had|celebrated)\s+(?:a|an|our|its)?\s*(?:traditional\s+|successful\s+)?ipo\b"
    r"|\b(?:our|its)\s+ipo\b|\bwent public\b|\binitial public offering\b"
    r"|\b(?:nasdaq|nyse)\s*:\s*[a-z]{1,5}\b|\b(?:is|are|'re)\s+a\s+publicly[- ]traded\b",
    re.I,
)
# "Series A-C startups" and "Series B companies" describe customers, not us.
_SERIES = re.compile(
    r"\b[Ss]eries[ -]([A-G])\d?\b"
    r"(?!\s*(?:[-–]|to|through)\s*[A-G]\b)"
    r"(?!\s+(?:startups|companies|founders)\b)"
)
_PRE_SEED = re.compile(r"\bpre[- ]seed\b", re.I)
_SEED = re.compile(
    r"\bseed[- ](?:stage|round|funding|funded|financing|investment|capital|investors)\b"
    r"|\b(?:raised|closed|secured|announced)\s+(?:a|an|our|its)?\s*"
    r"(?:\$[\d.,]+\s?\w+\s+)?seed\b",
    re.I,
)
_Y_COMBINATOR = re.compile(
    r"\by[ -]?combinator\b|\byc[- ]backed\b|\byc\s+[ws]\d\d\b", re.I
)
_VENTURE_BACKED = re.compile(
    r"\b(?:venture|vc)[- ](?:backed|funded)\b"
    r"(?!\s+(?:startups|companies|clients|businesses|portfolio|firms)\b)",
    re.I,
)
# Job ads also call a rare candidate "a unicorn"; only the company sense counts.
_UNICORN = re.compile(
    r"\bunicorn\s+status\b|\b(?:became|become|reached|achieved|hit)\s+(?:a\s+)?unicorn\b",
    re.I,
)

_AMOUNT = r"\$(\d[\d,]*(?:\.\d+)?)\s?(mm|m|bn|b|k|million|billion)\b\+?"
_QUALIFIERS = (
    r"(?:\s+(?:a|an|our|its|over|more than|nearly|approximately|about|roughly|just"
    r"|recently|successfully|additional|another|a further|a total of|total of|in excess of))*"
)
# After "raised $X in/of", only funding nouns count: not "in construction
# value", "of fund commitments", "in financial assistance", "in aggregate".
_NOT_A_RAISE = (
    r"(?!\s+(?:in|of)\s+(?!(?:funding|financing|capital|investment|venture|equity|total"
    r"|new|outside|private|fresh|additional|growth|seed|series|institutional|strategic"
    r"|recent|debt|early|late|its|our|a|an|the)\b))(?!\s+valuation\b)"
)
_RAISED_AMOUNT = re.compile(
    r"\b(?:raised|raising|raise|secured|securing|closed|backed by)\b"
    + _QUALIFIERS + r"\s+~?" + _AMOUNT + _NOT_A_RAISE,
    re.I,
)
_ROUND_GAP = (
    r"(?:\s+(?:in|of|at|total|new|additional|fresh|private|outside|venture|growth|equity"
    r"|strategic|raised|recent|institutional|late[- ]stage|early[- ]stage))*"
)
_AMOUNT_FOR_ROUND = re.compile(
    _AMOUNT + _ROUND_GAP + r"\s+(?:series[ -][a-g]|funding|round|raise|seed)\b", re.I
)
_UNIT_SCALE = {
    "k": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9,
}
_UNIT_LABEL = {
    "k": "K", "m": "M", "mm": "M", "million": "M", "b": "B", "bn": "B", "billion": "B",
}

_CRYPTO_WORD = re.compile(
    r"(?<![a-z0-9])(blockchain|cryptocurrenc(?:y|ies)|crypto|web3|defi|stablecoin"
    r"|on-chain|onchain)s?(?![a-z0-9])",
    re.I,
)


def funding_signals(text: str) -> dict[str, str]:
    """Stage and amount a posting states about its own company, or {}.

    ``funding_stage`` is normalized ("public", "pre-seed", "seed", "series a"
    .. "series g", "venture-backed", "unicorn"); ``total_funding`` is the
    largest amount sitting on raised/funding/Series wording ("$100M", "$1.37B").
    """
    found: dict[str, str] = {}
    if not text:
        return found
    stage = _stage_in(text)
    if stage:
        found["funding_stage"] = stage
    amount = _amount_in(text)
    if amount:
        found["total_funding"] = amount
    return found


def _ours(
    pattern: re.Pattern[str], text: str, others: re.Pattern[str] = _ABOUT_OTHERS
) -> list[re.Match[str]]:
    return [
        match for match in pattern.finditer(text)
        if not others.search(text, max(0, match.start() - _LOOKBACK), match.start())
    ]


def _stage_in(text: str) -> str | None:
    if _ours(_PUBLIC, text, others=_PUBLIC_OTHERS):
        return "public"
    letters = [match.group(1).lower() for match in _ours(_SERIES, text)]
    if letters:
        return f"series {max(letters)}"
    if _ours(_UNICORN, text):
        return "unicorn"
    if _ours(_PRE_SEED, text):
        return "pre-seed"
    if _ours(_SEED, text) or _ours(_Y_COMBINATOR, text):
        return "seed"
    if _ours(_VENTURE_BACKED, text):
        return "venture-backed"
    return None


def _amount_in(text: str) -> str | None:
    best: tuple[float, str] | None = None
    for pattern in (_RAISED_AMOUNT, _AMOUNT_FOR_ROUND):
        for match in _ours(pattern, text):
            number = match.group(1).replace(",", "")
            unit = match.group(2).lower()
            value = float(number) * _UNIT_SCALE[unit]
            if best is None or value > best[0]:
                best = (value, f"${number}{_UNIT_LABEL[unit]}")
    return best[1] if best else None


def industry_signals(company: str, text: str) -> list[str]:
    """["crypto"] when the company name carries a crypto word, or the text
    uses at least two distinct ones. One mention, however repeated, is not
    enough: a bank listing "blockchain" among initiatives is not a crypto job.
    """
    if _CRYPTO_WORD.search(company or ""):
        return ["crypto"]
    words = {_canonical(match.group(1)) for match in _CRYPTO_WORD.finditer(text or "")}
    return ["crypto"] if len(words) >= 2 else []


def _canonical(word: str) -> str:
    low = word.lower()
    return "cryptocurrency" if low.startswith("cryptocurrenc") else low


def fill_funding_from_text(job: dict[str, Any]) -> dict[str, Any]:
    """Fill a scraped job's empty funding fields from its description.

    Known-list companies (Amazon, Netflix) are skipped: a posting that names
    a round is talking about a customer or a fund, and the startup shelf
    trusts funding_stage on its own.
    """
    from job_finder.company_classifier import known_list_tier

    if job.get("funding_stage") and job.get("total_funding"):
        return job
    if known_list_tier(str(job.get("company") or "")):
        return job
    found = funding_signals(str(job.get("description") or ""))
    for key, value in found.items():
        if not job.get(key):
            job[key] = value
    return job
