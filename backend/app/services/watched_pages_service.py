"""Places I'd work at: add, list, and remove watched careers pages.

The page reading itself is core (job_finder.tools.scrapers.watched_pages);
this layer validates the pasted link, reads the page once so the user sees
what it holds, and stores it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from job_finder.models import watched_pages as store
from job_finder.tools.scrapers import watched_pages as source


class WatchedPageError(ValueError):
    """A pasted page could not be added. The message is user-facing."""


def normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        raise WatchedPageError("Paste a full link that starts with http:// or https://.")
    return url


def listing(db: Session, message: str = "") -> dict:
    pages = store.list_pages(db)
    watched = {p["url"].rstrip("/").lower() for p in pages}
    suggestions = [
        s for s in source.starter_list() if s["url"].rstrip("/").lower() not in watched
    ]
    return {"pages": pages, "suggestions": suggestions, "message": message}


def _found_message(kept: int, found: int) -> str:
    if found == 0:
        return "No openings on that page right now. Checked again every refresh."
    if kept == 0:
        return (
            f"{found} opening{'s' if found != 1 else ''} on the page, "
            "none part-time near you yet. Checked again every refresh."
        )
    return (
        f"{kept} part-time opening{'s' if kept != 1 else ''} near you. "
        "They land on the board at the next refresh."
    )


def add_page(db: Session, raw_url: str, place: str | None = None) -> dict:
    url = normalize_url(raw_url)
    checked = source.check_page(url, place)
    if checked["error"]:
        raise WatchedPageError(checked["error"])
    kept = len(checked["rows"])
    store.save_page(db, url, checked["name"], kept)
    return listing(db, _found_message(kept, int(checked["found"])))


def remove_page(db: Session, page_id: int) -> dict:
    store.remove_page(db, page_id)
    return listing(db)
