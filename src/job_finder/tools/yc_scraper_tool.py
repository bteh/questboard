"""Backward-compat shim — re-exports search_yc_jobs from scraper registry."""

from __future__ import annotations

from job_finder.tools.scrapers.yc_workatastartup import search_yc_jobs

__all__ = ["search_yc_jobs"]
