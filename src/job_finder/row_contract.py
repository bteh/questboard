"""The row contract: a listing publishes only when it is actionable.

The curation audit (2026-07-10, docs/source-coverage.md) found three ways
a structurally healthy source can still break the board's promise: a blog
article published as a casting call, a moderation placeholder as a title,
and discussion threads standing in for a place to act. Health checks ask
"is the pipe flowing"; this module asks "is what is flowing drinkable",
per row, before anything lands.

Shared structural rules apply to every row. URL host/path gates are
per-source declarations on the registry entry (a source states what is
true about ITSELF; bankrewards points outward at bank domains by design,
so it declares no host gate). Invalid rows are dropped and counted as
rows_invalid in the scrape run log, so a validator that suddenly rejects
everything is as visible as a source that broke.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# moderation placeholders and empty shells are never a specific ask
_PLACEHOLDER_TITLE_RE = re.compile(
    r"^\s*\[?\s*(removed|deleted)(\s+by\s+moderator)?\s*\]?\s*$", re.IGNORECASE
)

_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host_allowed(netloc: str, allowed: tuple[str, ...]) -> bool:
    host = netloc.lower().split(":", 1)[0]
    return any(host == domain or host.endswith("." + domain) for domain in allowed)


def validate_row(row: dict, meta, now: datetime | None = None) -> str | None:
    """The reason this row may not publish, or None when it may.

    ``meta`` needs only ``allowed_url_hosts`` and ``allowed_url_paths``
    (a ScraperMeta works; so does any object with those attributes).
    """
    title = str(row.get("title") or "").strip()
    if not title:
        return "missing_title"
    if _PLACEHOLDER_TITLE_RE.match(title):
        return "placeholder_title"

    url = str(row.get("url") or "").strip()
    allowed_hosts = getattr(meta, "allowed_url_hosts", None)
    allowed_paths = getattr(meta, "allowed_url_paths", None)
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "malformed_url"
        if allowed_hosts and not _host_allowed(parsed.netloc, allowed_hosts):
            return "host_not_allowed"
        if allowed_paths and not any(parsed.path.startswith(p) for p in allowed_paths):
            return "path_not_allowed"
    elif allowed_hosts or allowed_paths:
        # a source that declares where its rows point must always point
        return "missing_url"

    date_posted = str(row.get("date_posted") or "").strip()
    if date_posted:
        match = _DATE_PREFIX_RE.match(date_posted)
        if match:
            try:
                stated = datetime(int(match[1]), int(match[2]), int(match[3]))
            except ValueError:
                return "malformed_date"
            # one day of slack for timezone edges; beyond that a future
            # post date is fiction
            if stated > (now or _utcnow()) + timedelta(days=1):
                return "future_date"

    return None


def validate_rows(
    rows: list[dict], meta, now: datetime | None = None
) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Split rows into (publishable, rejected-with-reason)."""
    moment = now or _utcnow()
    valid: list[dict] = []
    rejected: list[tuple[dict, str]] = []
    for row in rows:
        reason = validate_row(row, meta, moment)
        if reason is None:
            valid.append(row)
        else:
            rejected.append((row, reason))
    return valid, rejected
