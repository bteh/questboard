"""Places I'd work at: careers pages the user asked Questboard to check.

A shop that posts jobs only on its own site (ELOREA's Shopify careers page,
Oct 8 2026) never reaches Indeed, so the user pastes the page here and every
quest refresh reads it (scrapers/watched_pages.py). Local-only: the hosted
board never runs a visitor's private list.

Kept apart from the company watchlist on purpose. That list stores ATS board
tokens per workspace and feeds the career pipeline; a watched page is a plain
URL that feeds the part-time lane and is read by a scraper that has no
workspace in hand.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from job_finder.models.database import Base

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchedPageRecord(Base):
    __tablename__ = "watched_pages"

    id = Column(Integer, primary_key=True)
    url = Column(String(1000), nullable=False, unique=True)
    name = Column(String(200), default="")
    added_at = Column(DateTime, default=_utcnow)
    last_checked_at = Column(DateTime, nullable=True)
    # openings kept for the part-time lane on the last check
    last_found = Column(Integer, default=0)
    last_error = Column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "name": self.name or "",
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "last_checked_at": (
                self.last_checked_at.isoformat() if self.last_checked_at else None
            ),
            "last_found": int(self.last_found or 0),
            "last_error": self.last_error or "",
        }


def list_pages(session: Session) -> list[dict]:
    rows = session.query(WatchedPageRecord).order_by(WatchedPageRecord.id).all()
    return [row.to_dict() for row in rows]


def save_page(
    session: Session, url: str, name: str, found: int, error: str = ""
) -> dict:
    """Insert the page, or refresh its name and last check when it exists."""
    row = session.query(WatchedPageRecord).filter(WatchedPageRecord.url == url).first()
    if row is None:
        row = WatchedPageRecord(url=url)
        session.add(row)
    row.name = (name or "")[:200]
    row.last_checked_at = _utcnow()
    row.last_found = int(found)
    row.last_error = error or ""
    session.commit()
    return row.to_dict()


def remove_page(session: Session, page_id: int) -> bool:
    row = session.get(WatchedPageRecord, page_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def load_watched_pages() -> list[dict]:
    """Every watched page, for the scraper. Empty on any failure."""
    from job_finder.models.database import get_session

    try:
        session = get_session()
    except Exception:
        return []
    try:
        return list_pages(session)
    except Exception:
        logger.warning("watched pages: read failed", exc_info=True)
        return []
    finally:
        session.close()


def record_checks(checks: list[dict]) -> None:
    """Stamp each page's last check ({url, found, error}). Never raises."""
    if not checks:
        return
    from job_finder.models.database import get_session

    try:
        session = get_session()
    except Exception:
        return
    try:
        by_url = {str(c.get("url")): c for c in checks}
        rows = (
            session.query(WatchedPageRecord)
            .filter(WatchedPageRecord.url.in_(list(by_url)))
            .all()
        )
        now = _utcnow()
        for row in rows:
            check = by_url[row.url]
            row.last_checked_at = now
            row.last_found = int(check.get("found") or 0)
            row.last_error = str(check.get("error") or "")[:500]
        session.commit()
    except Exception:
        logger.warning("watched pages: check stamp failed", exc_info=True)
        session.rollback()
    finally:
        session.close()
