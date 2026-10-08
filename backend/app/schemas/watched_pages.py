from __future__ import annotations

from pydantic import BaseModel


class WatchedPage(BaseModel):
    id: int
    url: str
    name: str = ""
    added_at: str | None = None
    last_checked_at: str | None = None
    last_found: int = 0
    last_error: str = ""


class WatchedPageSuggestion(BaseModel):
    name: str
    url: str
    area: str = ""
    hosting: str = ""
    note: str = ""


class WatchedPageAddRequest(BaseModel):
    url: str = ""


class WatchedPagesResponse(BaseModel):
    """The user's watched careers pages plus starter suggestions not yet added.

    ``message`` is set after an add: what one read of the page found.
    """
    pages: list[WatchedPage] = []
    suggestions: list[WatchedPageSuggestion] = []
    message: str = ""
