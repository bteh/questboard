"""Company watchlist endpoints — add/remove target companies with ATS auto-discovery."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.watchlist import WatchlistAddRequest, WatchlistResponse
from app.services import watchlist_service
from app.dependencies import reject_legacy_route_in_hosted_mode, sanitize_profile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["watchlist"])


@router.get("/profiles/{profile}/watchlist", response_model=WatchlistResponse)
async def get_watchlist(profile: str):
    """Get the company watchlist for a profile."""
    reject_legacy_route_in_hosted_mode("Profile watchlists are disabled in hosted mode")
    profile = sanitize_profile(profile)
    return watchlist_service.get_watchlist(profile)


@router.post("/profiles/{profile}/watchlist", response_model=WatchlistResponse)
async def add_company(profile: str, req: WatchlistAddRequest):
    """Add a company to the watchlist by name or careers link.

    A careers link (Greenhouse, Lever, Ashby, Workday) stores its exact
    board token after one verification probe; an unsupported or
    unconfirmable link is a 422. A bare name runs auto-discovery; when
    discovery fails, the response ``message`` says so.
    """
    reject_legacy_route_in_hosted_mode("Profile watchlists are disabled in hosted mode")
    profile = sanitize_profile(profile)
    name = req.name.strip()
    url = req.url.strip()
    if not name and not url:
        raise HTTPException(400, "Company name or careers link is required")
    try:
        return watchlist_service.add_company(profile, name, url)
    except watchlist_service.BoardUrlError as e:
        raise HTTPException(422, detail=str(e))
    except Exception as e:
        logger.exception("Failed to add company to watchlist")
        raise HTTPException(500, detail=str(e))


@router.delete("/profiles/{profile}/watchlist/{name}", response_model=WatchlistResponse)
async def remove_company(profile: str, name: str):
    """Remove a company from the watchlist."""
    reject_legacy_route_in_hosted_mode("Profile watchlists are disabled in hosted mode")
    profile = sanitize_profile(profile)
    try:
        return watchlist_service.remove_company(profile, name)
    except Exception as e:
        logger.exception("Failed to remove company from watchlist")
        raise HTTPException(500, detail=str(e))
