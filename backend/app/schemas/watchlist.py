from __future__ import annotations

from pydantic import BaseModel


class WatchlistCompany(BaseModel):
    """A company the user wants to track."""
    name: str                   # Display name: "Netflix"
    slug: str = ""              # ATS board slug: "netflix"
    ats: str = ""               # "greenhouse" | "lever" | "ashby" | "unknown"
    job_count: int = 0          # Last known open job count
    careers_url: str = ""       # Direct link to career page


class WatchlistAddRequest(BaseModel):
    """Request to add a company to the watchlist."""
    name: str


class WatchlistResponse(BaseModel):
    """Full watchlist for a profile."""
    profile: str
    companies: list[WatchlistCompany] = []
