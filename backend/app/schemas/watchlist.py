from __future__ import annotations

from pydantic import BaseModel


class WatchlistCompany(BaseModel):
    """A company the user wants to track."""
    name: str                   # Display name: "Netflix"
    slug: str = ""              # ATS board token: "netflix" (workday: "tenant/site")
    ats: str = ""               # "greenhouse" | "lever" | "ashby" | "workday" | "unknown"
    job_count: int = 0          # Last known open job count
    careers_url: str = ""       # Direct link to career page


class WatchlistAddRequest(BaseModel):
    """Request to add a company: a name, a careers link, or both."""
    name: str = ""
    url: str = ""


class WatchlistResponse(BaseModel):
    """Full watchlist for a profile.

    ``message`` is set when an add finished in an incomplete state (no job
    board found for the name), so the caller can ask for the careers link
    instead of presenting the inert entry as healthy.
    """
    profile: str
    companies: list[WatchlistCompany] = []
    message: str = ""
