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
    error_sample: str = ""


class ScrapeRunsResponse(BaseModel):
    runs: list[ScrapeRunEntry]
