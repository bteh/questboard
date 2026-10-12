"""Posting fingerprint that decides whether an assistant verdict is still current.

The date is hashed in its normalized shape, so a format-only rewrite of
date_posted (the Sep 22 2026 calendar repair threw away 143 verdicts) keeps
the verdict. Verdicts stamped before this used the raw date text; they stay
current while the posting is otherwise unchanged.
"""

from __future__ import annotations

import hashlib
from typing import Any

from job_finder.tools.scrapers._utils import normalize_posted_date


def _hash(record: Any, date_posted: Any) -> str:
    payload = "\n".join(
        str(value or "")
        for value in (
            record.job_title,
            record.company,
            record.location,
            record.description,
            date_posted,
            record.job_url,
            record.work_type,
            record.remote_scope,
            record.salary_min,
            record.salary_max,
            record.salary_min_annualized,
            record.salary_max_annualized,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(record: Any) -> str:
    return _hash(record, normalize_posted_date(record.date_posted))


def legacy_content_hash(record: Any) -> str:
    return _hash(record, record.date_posted)


def fingerprint_matches(record: Any, stored: Any) -> bool:
    if not stored:
        return False
    return stored == content_hash(record) or stored == legacy_content_hash(record)
