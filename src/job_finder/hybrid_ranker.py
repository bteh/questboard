"""Deterministic career-job retrieval with optional local semantic evidence.

The ranker never calls an LLM and never exposes its raw fusion score. It uses
weighted reciprocal-rank fusion (k=60) over BM25, BGE cosine when available,
and structured intent signals. Results carry a small set of auditable reasons
for the UI instead of a misleading similarity percentage.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]*")
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "with", "you",
})
_K = 60


def tokenize(text: str | None) -> list[str]:
    return [token for token in _TOKEN_RE.findall((text or "").lower()) if token not in _STOP]


def _job_text(job: Mapping[str, Any]) -> str:
    # Repeating the title makes a title match matter more than boilerplate in
    # a long description without introducing a profile-specific heuristic.
    title = str(job.get("title") or job.get("job_title") or "")
    return " ".join((title, title, title, str(job.get("company") or ""), str(job.get("description") or "")))


def bm25_scores(query: str, documents: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Small dependency-free Okapi BM25 implementation for one candidate set."""
    query_terms = list(dict.fromkeys(tokenize(query)))
    tokenized = [tokenize(document) for document in documents]
    if not query_terms or not tokenized:
        return [0.0] * len(documents)
    avg_len = sum(len(doc) for doc in tokenized) / max(len(tokenized), 1)
    avg_len = avg_len or 1.0
    doc_freq = {
        term: sum(1 for doc in tokenized if term in set(doc))
        for term in query_terms
    }
    count = len(tokenized)
    scores: list[float] = []
    for doc in tokenized:
        tf = Counter(doc)
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            df = doc_freq[term]
            idf = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1.0 - b + b * len(doc) / avg_len)
            score += idf * (freq * (k1 + 1.0)) / denom
        scores.append(score)
    return scores


def _contains_phrase(text: str, values: Sequence[str]) -> str | None:
    low = text.lower()
    return next((value for value in values if value.strip() and value.lower() in low), None)


def _structured(job: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[float, list[dict[str, str]]]:
    roles = [str(v).strip() for v in config.get("target_roles", []) if str(v).strip()]
    keywords = [str(v).strip() for v in config.get("keyword_searches", []) if str(v).strip()]
    companies = [
        str(v.get("name") if isinstance(v, dict) else v).strip()
        for v in config.get("watchlist", [])
        if str(v.get("name") if isinstance(v, dict) else v).strip()
    ]
    title = str(job.get("title") or job.get("job_title") or "")
    company = str(job.get("company") or "")
    combined = _job_text(job)
    score = 0.0
    reasons: list[dict[str, str]] = []

    matched_role = _contains_phrase(title, roles)
    if matched_role:
        score += 5.0
        reasons.append({"code": "target_role", "label": f"Title matches {matched_role}"})
    elif roles:
        role_terms = set(tokenize(" ".join(roles)))
        overlap = role_terms & set(tokenize(title))
        if overlap:
            score += min(3.0, 1.0 + len(overlap))
            reasons.append({"code": "role_family", "label": "Title is in your target role family"})

    keyword_hits = [keyword for keyword in keywords if keyword.lower() in combined.lower()]
    if keyword_hits:
        score += min(4.0, 1.0 + len(keyword_hits))
        shown = ", ".join(keyword_hits[:2])
        reasons.append({"code": "keyword_overlap", "label": f"Uses your keywords: {shown}"})

    target_company = _contains_phrase(company, companies)
    if target_company:
        score += 2.5
        reasons.append({"code": "target_company", "label": "At a company you targeted"})

    loc = config.get("location_preferences") or {}
    workplace = str(loc.get("workplace_preference") or "")
    is_remote = bool(job.get("is_remote")) or str(job.get("work_type") or "").lower() == "remote"
    if (workplace in {"remote_friendly", "remote_only"} and is_remote) or (
        workplace == "location_only" and not is_remote
    ):
        score += 1.5
        reasons.append({"code": "workplace", "label": "Fits your workplace preference"})

    comp = config.get("compensation") or {}
    floor = float(comp.get("min_base") or 0)
    salary_hi = job.get("salary_max_annualized") or job.get("salary_max")
    salary_lo = job.get("salary_min_annualized") or job.get("salary_min")
    if floor and (salary_hi or salary_lo) and float(salary_hi or salary_lo) >= floor:
        score += 1.5
        reasons.append({"code": "compensation", "label": "Stated pay clears your floor"})

    return score, reasons


def _ranks(values: Sequence[float], *, missing: set[int] | None = None) -> list[int]:
    missing = missing or set()
    ordered = sorted((i for i in range(len(values)) if i not in missing), key=lambda i: (-values[i], i))
    ranks = [len(values) + 1] * len(values)
    previous: float | None = None
    tied_rank = 0
    for position, index in enumerate(ordered, 1):
        if previous is None or values[index] != previous:
            tied_rank = position
            previous = values[index]
        ranks[index] = tied_rank
    return ranks


def rank_jobs(
    jobs: list[dict],
    *,
    query_text: str,
    config: Mapping[str, Any],
    semantic_scores: Mapping[int, float] | None = None,
) -> list[dict]:
    """Mutate and order jobs using weighted RRF; deterministic on equal input."""
    if not jobs:
        return jobs
    lexical = bm25_scores(query_text, [_job_text(job) for job in jobs])
    structured_pairs = [_structured(job, config) for job in jobs]
    structured = [pair[0] for pair in structured_pairs]
    lexical_ranks = _ranks(lexical)
    structured_ranks = _ranks(structured)

    semantic_values: list[float] = []
    semantic_missing: set[int] = set()
    for index, job in enumerate(jobs):
        app_id = job.get("db_id")
        if semantic_scores is None or app_id not in semantic_scores:
            semantic_values.append(float("-inf"))
            semantic_missing.add(index)
        else:
            semantic_values.append(float(semantic_scores[app_id]))
    has_semantic = len(semantic_missing) < len(jobs)
    semantic_ranks = _ranks(semantic_values, missing=semantic_missing) if has_semantic else []

    for index, job in enumerate(jobs):
        if has_semantic:
            score = (
                0.45 / (_K + lexical_ranks[index])
                + 0.35 / (_K + semantic_ranks[index])
                + 0.20 / (_K + structured_ranks[index])
            )
            source = "hybrid"
        else:
            score = 0.70 / (_K + lexical_ranks[index]) + 0.30 / (_K + structured_ranks[index])
            source = "lexical"
        reasons = list(structured_pairs[index][1])
        if has_semantic and index not in semantic_missing and semantic_values[index] > 0.45:
            reasons.append({"code": "resume_semantic", "label": "The work described aligns with your resume"})
        if not reasons:
            reasons.append({"code": "retrieval", "label": "Relevant to your saved search terms"})
        job["rank_score"] = score
        job["rank_source"] = source
        job["match_bucket"] = job.get("match_bucket") or "primary"
        job["match_reasons"] = reasons[:3]

    jobs.sort(
        key=lambda job: (
            0 if job.get("match_bucket") == "primary" else 1,
            -float(job.get("rank_score") or 0),
            str(job.get("title") or job.get("job_title") or "").lower(),
        )
    )
    return jobs
