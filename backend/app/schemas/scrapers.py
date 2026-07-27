from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ScraperSource(BaseModel):
    name: str
    display_name: str
    url: str
    description: str
    category: str
    enabled_by_default: bool
    vertical: str = "career"


class SourceHealthEntry(BaseModel):
    source: str
    display_name: str
    vertical: str
    # ok | zero_rows | dropped | failing | quiet (see job_finder.source_health)
    verdict: str
    last_run_at: datetime | None = None
    last_finish_reason: str
    last_rows: int
    median_rows: int
    runs_seen: int
    error_sample: str = ""
    # What the source cost and what it delivered. `last_rows` is what it found;
    # `kept_rows` is what survived THIS person's roles, place, and pay and is
    # still on their board. The gap between them is a matter of fit, not
    # health, so the two are reported side by side and neither is a verdict.
    last_seconds: float = 0.0
    kept_rows: int = 0


class SourceHealthResponse(BaseModel):
    sources: list[SourceHealthEntry]
    # sources whose latest run needs a human: failing, zero_rows, dropped
    needs_attention: int


class ScrapeRunEntry(BaseModel):
    source: str
    display_name: str
    vertical: str
    started_at: datetime | None = None
    duration_s: float
    # ok | zero_rows | exception | timeout
    finish_reason: str
    rows_found: int
    # rows the row contract rejected before they could land
    rows_invalid: int = 0
    error_sample: str = ""


class ScrapeRunsResponse(BaseModel):
    runs: list[ScrapeRunEntry]


class SourceScheduleEntry(BaseModel):
    source: str
    display_name: str
    vertical: str
    refresh_hours: int
    last_attempt_at: datetime | None = None
    # None means the source has never run and is due immediately
    due_at: datetime | None = None
    due_now: bool
    # consecutive failed runs, and whether the breaker is backing this
    # source off after too many in a row
    failure_streak: int = 0
    breaker_open: bool = False


class BoardScheduleResponse(BaseModel):
    scheduler_running: bool
    sources: list[SourceScheduleEntry]
