from fastapi import APIRouter

from app.api import (
    analytics,
    applications,
    dev_auth,
    health,
    locations,
    me,
    onboarding,
    resume,
    schedule,
    scrapers,
    search,
    session,
    settings,
    watchlist,
)

api_router = APIRouter()

# Health routes (no prefix)
api_router.include_router(health.router)

# API v1 routes
api_router.include_router(applications.router, prefix="/api/v1")
api_router.include_router(analytics.router, prefix="/api/v1")
api_router.include_router(dev_auth.router, prefix="/api/v1")
api_router.include_router(me.router, prefix="/api/v1")
api_router.include_router(search.router, prefix="/api/v1")
api_router.include_router(session.router, prefix="/api/v1")
api_router.include_router(onboarding.router, prefix="/api/v1")
api_router.include_router(locations.router, prefix="/api/v1")
api_router.include_router(settings.router, prefix="/api/v1")
api_router.include_router(resume.router, prefix="/api/v1")
api_router.include_router(schedule.router, prefix="/api/v1")
api_router.include_router(scrapers.router, prefix="/api/v1")
api_router.include_router(watchlist.router, prefix="/api/v1")
