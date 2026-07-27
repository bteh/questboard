"""Per-source health from the scrape run log.

A scraper that silently breaks is the board's biggest trust risk: a site
redesign that returns 0 rows, or half the usual volume, looks exactly like
a quiet day. The verdicts here compare each source's latest run against its
own recent history (a relative baseline, not a fixed floor), so triage is
"read one list" instead of spelunking logs.

Verdicts:
- ok        the latest run finished and its volume is in line with history
- zero_rows the latest run finished with 0 rows while history says it
            normally finds some (the classic silent-breakage signature)
- dropped   the latest run found less than half the source's recent median
            (only when the median is big enough to make halving meaningful)
- failing   the latest run raised or timed out
- quiet     the source has found nothing recently, including now; honest
            low supply, not breakage
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

# A median below this is too thin for the 50% drop rule to mean anything;
# a 3-row source dipping to 1 is noise, not a redesign.
MIN_MEDIAN_FOR_DROP_RULE = 8
DROP_FRACTION = 0.5


@dataclass
class SourceHealth:
    source: str
    vertical: str
    verdict: str
    last_run_at: datetime | None
    last_finish_reason: str
    last_rows: int
    median_rows: int
    runs_seen: int
    error_sample: str
    # What the latest run cost in wall-clock. Sources run concurrently, so the
    # slowest one sets the floor for the whole pull: worth seeing next to what
    # the source actually delivered.
    last_seconds: float = 0.0


def verdict_for(last_finish_reason: str, last_rows: int, median_rows: int) -> str:
    """The health verdict for a source's latest run against its history."""
    if last_finish_reason in ("exception", "timeout"):
        return "failing"
    if last_rows == 0:
        return "zero_rows" if median_rows > 0 else "quiet"
    if median_rows >= MIN_MEDIAN_FOR_DROP_RULE and last_rows < median_rows * DROP_FRACTION:
        return "dropped"
    return "ok"


def source_health(days: int = 14) -> list[SourceHealth]:
    """Health for every source with runs in the window, worst verdicts first."""
    from job_finder.models.database import get_recent_scrape_runs

    runs = get_recent_scrape_runs(days=days)
    by_source: dict[str, list] = {}
    for run in runs:  # newest first
        by_source.setdefault(run.source, []).append(run)

    out: list[SourceHealth] = []
    for source, rows in by_source.items():
        latest = rows[0]
        history = [r.rows_found for r in rows[1:] if r.finish_reason not in ("exception", "timeout")]
        med = int(median(history)) if history else 0
        out.append(
            SourceHealth(
                source=source,
                vertical=latest.vertical or "career",
                verdict=verdict_for(latest.finish_reason, latest.rows_found or 0, med),
                last_run_at=latest.started_at,
                last_finish_reason=latest.finish_reason,
                last_rows=latest.rows_found or 0,
                median_rows=med,
                runs_seen=len(rows),
                error_sample=latest.error_sample or "",
                last_seconds=round(float(latest.duration_s or 0.0), 1),
            )
        )

    order = {"failing": 0, "zero_rows": 1, "dropped": 2, "quiet": 3, "ok": 4}
    out.sort(key=lambda h: (order.get(h.verdict, 9), h.source))
    return out
