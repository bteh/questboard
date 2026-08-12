"""Cross-source duplicate detection shared by the pipeline and data repairs.

One home for the dedup key and the "same posting?" predicate, so the
in-memory search pipeline (job_finder.pipeline), the post-run DB merge
(backend pipeline_service), and the startup data repair
(job_finder.models.maintenance) can never drift apart on what counts as a
duplicate.

The key that catches the Alo case ("Aloyoga" on greenhouse vs "ALO" on
LinkedIn, different URLs, same Beverly Hills opening):

* company_key / title_key squash to alphanumeric-only after the usual
  normalization, so spacing and punctuation variants ("Alo Yoga" vs
  "Aloyoga") collide.
* companies_match additionally allows a guarded prefix match: "alo" matches
  "aloyoga", but a squashed name shorter than 3 characters never
  prefix-matches ("GE" must not swallow "Genentech").
* locations_compatible: both remote, or the same leading city token
  ("Beverly Hills, CA" vs "Beverly Hills, California, United States"), or
  one side unknown. Remote vs onsite and two different cities stay distinct.
* same_posting confirms with an ATS job token when both URLs carry one
  (gh_jid=8008047 on a company site equals /coinbase/jobs/8008047 on
  boards.greenhouse.io), else with the description similarity check.

Everything here is a pure function over plain job dicts with the pipeline's
field names (title, company, location, is_remote, url, description, source).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlparse

from job_finder.job_trust import is_direct_source

logger = logging.getLogger(__name__)

_ALNUM_RE = re.compile(r"[^a-z0-9]")

# The shortest squashed company name allowed to prefix-match a longer one.
# "alo" (3) may match "aloyoga"; "ge" (2) may never match "genentech".
_MIN_PREFIX_LEN = 3

# Statuses a repair or auto-merge may collapse as duplicate losers. Anything
# else (clipped, applied, interviewing, ...) records user work and always
# survives its cluster.
COLLAPSIBLE_STATUSES: frozenset[str] = frozenset({"", "found", "reviewed"})


def normalize_company(name: str) -> str:
    """Normalize a company name for dedup comparison (spaced form)."""
    if not name:
        return ""
    t = name.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    # Remove common corporate suffixes
    for suffix in (
        ", inc.", ", inc", ", llc", ", corp.", ", corp", ", ltd.", ", ltd",
        ", limited", ", co.", " inc.", " inc", " llc", " corp.", " corp",
        " ltd.", " ltd", " limited", " co.", " gmbh", " ag", " plc",
        " sa", " sas", " bv", " s.a.", " s.r.l.",
    ):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    # Strip non-alphanumeric, collapse whitespace
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_title(title: str) -> str:
    """Normalize a job title for dedup comparison (spaced form)."""
    if not title:
        return ""
    t = title.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    # Remove common level prefixes/suffixes that vary across sources
    t = re.sub(r"\b(sr\.?|senior|jr\.?|junior|lead|principal|staff)\b", lambda m: {
        "sr": "senior", "sr.": "senior", "jr": "junior", "jr.": "junior",
    }.get(m.group(0).lower(), m.group(0).lower()), t)
    # Strip non-alphanumeric, collapse whitespace
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_location(location: str) -> str:
    """Normalize a location string for dedup comparison."""
    if not location:
        return ""
    t = unicodedata.normalize("NFKD", location.lower().strip())
    if "remote" in t:
        return "remote"
    if "hybrid" in t:
        return "hybrid"
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_description(text: str) -> str:
    """Normalize descriptions so obviously identical postings cluster together."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text.lower())
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def company_key(name: str) -> str:
    """Alphanumeric-squashed company key: "Alo Yoga" and "Aloyoga" collide."""
    return _ALNUM_RE.sub("", normalize_company(name))


def title_key(title: str) -> str:
    """Alphanumeric-squashed title key."""
    return _ALNUM_RE.sub("", normalize_title(title))


def companies_match(key_a: str, key_b: str) -> bool:
    """Whether two squashed company keys name the same company.

    Exact match, or a guarded prefix match: aggregators shorten brand names
    ("ALO" for "Aloyoga"), so one key may be a prefix of the other as long as
    the shorter side has at least _MIN_PREFIX_LEN characters. Combined with
    the title and location gates this stays safe; on its own a prefix match
    would be far too eager.
    """
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    shorter, longer = sorted((key_a, key_b), key=len)
    return len(shorter) >= _MIN_PREFIX_LEN and longer.startswith(shorter)


def city_token(location: str) -> str:
    """Leading city token of a location string, normalized.

    "Beverly Hills, California, United States" and "Beverly Hills, CA" both
    yield "beverly hills"; an empty/unknown location yields "".
    """
    head = (location or "").split(",")[0]
    head = re.sub(r"[^a-z0-9\s]", " ", head.lower())
    return re.sub(r"\s+", " ", head).strip()


def loc_is_remote(job: dict) -> bool:
    if job.get("is_remote"):
        return True
    loc = (job.get("location") or "").lower()
    return any(k in loc for k in ("remote", "anywhere", "worldwide", "distributed"))


def locations_compatible(a: dict, b: dict) -> bool:
    """Could two same-company/title jobs be the same posting, by location?

    Remote/remote is compatible; remote vs onsite is not. Two onsite jobs are
    compatible when their leading city tokens agree (state/country spelling
    may differ across boards) or one side has no location at all. Two
    different cities are distinct openings.
    """
    a_rem, b_rem = loc_is_remote(a), loc_is_remote(b)
    if a_rem and b_rem:
        return True
    if a_rem != b_rem:
        return False
    tok_a = city_token(a.get("location", ""))
    tok_b = city_token(b.get("location", ""))
    if not tok_a or not tok_b:
        return True
    return tok_a == tok_b


def descriptions_look_duplicate(left: str, right: str) -> bool:
    """Return True only when two descriptions look like the same posting."""
    left_norm = normalize_description(left)
    right_norm = normalize_description(right)
    if not left_norm or not right_norm:
        return False

    shorter, longer = sorted((left_norm, right_norm), key=len)
    if len(shorter) >= 120 and shorter in longer:
        return True

    return SequenceMatcher(
        None,
        left_norm[:1600],
        right_norm[:1600],
    ).ratio() >= 0.82


def short_or_empty_description(text: str) -> bool:
    """True when a description is too thin to disprove a cross-board duplicate."""
    return len(normalize_description(text or "")) < 120


def ats_job_token(url: str) -> tuple[str, str] | None:
    """Stable (ats, job_id) identity parsed from a job URL, when present.

    A greenhouse posting keeps its numeric id across URL shapes: a company
    careers page carries it as ?gh_jid=<id>, greenhouse.io hosts it at
    .../jobs/<id>. Lever and Ashby use company/posting path pairs. Two URLs
    with the same token are the same posting; two tokens from the same ATS
    that differ are two different postings.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if not host:
        return None

    gh_jid = parse_qs(parsed.query or "").get("gh_jid", [])
    if gh_jid and gh_jid[0].strip().isdigit():
        return ("greenhouse", gh_jid[0].strip())

    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if host.endswith("greenhouse.io"):
        for i, seg in enumerate(segments):
            if seg == "jobs" and i + 1 < len(segments) and segments[i + 1].isdigit():
                return ("greenhouse", segments[i + 1])
    if host.endswith("lever.co") and len(segments) >= 2:
        return ("lever", f"{segments[0].lower()}/{segments[1].lower()}")
    if host.endswith("ashbyhq.com") and len(segments) >= 2:
        return ("ashby", f"{segments[0].lower()}/{segments[1].lower()}")
    return None


def same_posting(a: dict, b: dict) -> bool:
    """Cross-board duplicate detection: the same opening from different sources.

    Location must be compatible first. Then, when both sides carry an ATS job
    token, the tokens decide both ways (equal ids merge even when the two
    boards rewrote the description; different ids are two real openings).
    Without tokens, merges happen when the descriptions look like the same
    posting or one side's description is too thin to disprove it. Two
    substantial-but-different descriptions at a compatible location are
    treated as distinct roles (no over-merge).
    """
    if not locations_compatible(a, b):
        return False
    token_a = ats_job_token(a.get("url", ""))
    token_b = ats_job_token(b.get("url", ""))
    if token_a and token_b:
        return token_a == token_b
    desc_a = a.get("description", "")
    desc_b = b.get("description", "")
    if descriptions_look_duplicate(desc_a, desc_b):
        return True
    if short_or_empty_description(desc_a) or short_or_empty_description(desc_b):
        return True
    return False


# Prefer sources that tend to have richer descriptions (aggregator tiers).
_SOURCE_RANK = {
    "indeed": 5, "linkedin": 4,
    "greenhouse": 4, "lever": 4, "ashby": 4, "workday": 4,
    "glassdoor": 3, "workatastartup": 3,
    "remotive": 2, "himalayas": 2, "remoteok": 2, "hackernews": 2,
    "weworkremotely": 2, "cryptojobslist": 2, "web3career": 2, "arbeitnow": 2,
    "themuse": 2, "zip_recruiter": 2, "google": 1,
}


def richness_key(job: dict) -> tuple:
    """Sort key for picking a duplicate cluster's keeper (bigger wins).

    A direct ATS/company source always beats an aggregator copy of the same
    posting; among equals, stated pay, then description length, then having a
    URL at all, then the source's usual richness tier.
    """
    desc_len = len(job.get("description") or "")
    has_salary = 1 if (job.get("salary_min") or job.get("salary_max")) else 0
    has_url = 1 if job.get("url") else 0
    direct = 1 if is_direct_source(job.get("source")) else 0
    src = _SOURCE_RANK.get((job.get("source") or "").lower(), 0)
    return (direct, has_salary, desc_len, has_url, src)


def is_protected_status(status: str | None) -> bool:
    """True when a row's status records user work and must never be a loser."""
    return (status or "").strip().lower() not in COLLAPSIBLE_STATUSES


def cluster_jobs(jobs: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    """Group jobs into same-posting clusters.

    Returns (clusters, keyless): clusters covers every job that has both a
    company and a title (singletons included); keyless holds jobs missing
    either, which can never be safely deduplicated.

    Jobs are bucketed by squashed title, sub-grouped by companies_match (a
    connected-component pass, so "ALO" and "Aloyoga" land together), then
    chained into posting clusters with same_posting.
    """
    buckets: dict[str, list[tuple[str, dict]]] = {}
    keyless: list[dict] = []
    for job in jobs:
        ckey = company_key(job.get("company", ""))
        tkey = title_key(job.get("title", ""))
        if ckey and tkey:
            buckets.setdefault(tkey, []).append((ckey, job))
        else:
            keyless.append(job)

    clusters: list[list[dict]] = []
    for members in buckets.values():
        # Connected components over companies_match. Transitively, a short
        # key can bridge two longer ones ("alo" links "aloyoga" and
        # "alosecurity"); with the title and same_posting gates still ahead,
        # staying transitive here is simpler and safe enough.
        parent = list(range(len(members)))

        def _find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if companies_match(members[i][0], members[j][0]):
                    parent[_find(i)] = _find(j)

        company_groups: dict[int, list[dict]] = {}
        for i, (_, job) in enumerate(members):
            company_groups.setdefault(_find(i), []).append(job)

        for group in company_groups.values():
            posting_clusters: list[list[dict]] = []
            for job in group:
                placed = False
                for cluster in posting_clusters:
                    if same_posting(job, cluster[0]):
                        cluster.append(job)
                        placed = True
                        break
                if not placed:
                    posting_clusters.append([job])
            clusters.extend(posting_clusters)

    return clusters, keyless


def describe_collapse(keeper: dict, losers: list[dict]) -> str:
    """One-line log message for a collapsed duplicate cluster."""
    kept = (
        f"kept {keeper.get('source') or '?'} "
        f"'{keeper.get('company', '')} / {keeper.get('title', '')}' "
        f"({keeper.get('url') or 'no url'})"
    )
    dropped = ", ".join(
        f"{j.get('source') or '?'} ({j.get('url') or 'no url'})" for j in losers
    )
    return f"cross-source dedup: {kept}; collapsed {len(losers)} duplicate(s): {dropped}"
