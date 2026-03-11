"""Settings and configuration endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

from app.schemas.settings import (
    DatabaseInfo,
    FetchModelsRequest,
    LLMConfig,
    LLMStatus,
    LLMTestResult,
    ProfileDetail,
    ProfilePreferences,
    ProfilePreferencesResponse,
    ProfileSummary,
    ProviderModel,
    ProviderPreset,
)
from app.services import settings_service

router = APIRouter(tags=["settings"])


# --- LLM Configuration ---


@router.get("/settings/llm", response_model=LLMStatus)
async def get_llm_config():
    """Get current LLM configuration and connection status."""
    return settings_service.get_llm_status()


@router.put("/settings/llm", response_model=LLMStatus)
async def update_llm_config(config: LLMConfig):
    """Update LLM provider configuration."""
    try:
        return settings_service.update_llm_config(
            provider=config.provider,
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
        )
    except Exception as e:
        logger.exception("Failed to update LLM config")
        raise HTTPException(500, detail=str(e))


@router.post("/settings/llm/test", response_model=LLMTestResult)
async def test_llm_connection():
    """Test the current LLM connection."""
    return settings_service.test_llm_connection()


@router.post("/settings/llm/models", response_model=list[ProviderModel])
async def fetch_provider_models(req: FetchModelsRequest):
    """Fetch available models from a provider's /models endpoint.

    Proxies the request so the frontend doesn't need CORS access to
    arbitrary provider URLs.
    """
    import requests as http_requests

    base = req.base_url.rstrip("/")
    headers: dict[str, str] = {}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key}"

    try:
        resp = http_requests.get(f"{base}/models", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("Failed to fetch models from %s: %s", base, e)
        return []

    # OpenAI-compatible /models returns { "data": [ { "id": "..." }, ... ] }
    models_raw = data.get("data", []) if isinstance(data, dict) else data
    if not isinstance(models_raw, list):
        return []

    results: list[ProviderModel] = []
    for m in models_raw:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id", "")
        if not model_id:
            continue
        # Use the model ID as the display name, cleaned up slightly
        name = m.get("name") or m.get("id", "")
        results.append(ProviderModel(id=model_id, name=name))

    # Sort alphabetically by id
    results.sort(key=lambda x: x.id)
    return results


@router.get("/settings/llm/presets", response_model=list[ProviderPreset])
async def get_llm_presets(include_internal: bool = False):
    """List available LLM provider presets.

    Pass ``?include_internal=true`` to include proxy/internal presets.
    """
    return settings_service.get_provider_presets(include_internal=include_internal)


# --- Database ---


@router.get("/settings/database", response_model=DatabaseInfo)
async def get_database_info():
    """Get database path, size, and record count."""
    return settings_service.get_database_info()


# --- Profiles ---


@router.get("/profiles", response_model=list[ProfileSummary])
async def list_profiles():
    """List available search profiles."""
    return settings_service.list_profiles()


@router.get("/profiles/{name}", response_model=ProfileDetail)
async def get_profile(name: str):
    """Get full config for a profile."""
    detail = settings_service.get_profile_detail(name)
    if not detail:
        raise HTTPException(404, f"Profile '{name}' not found")
    return detail


@router.get("/profiles/{name}/preferences", response_model=ProfilePreferencesResponse)
async def get_profile_preferences(name: str):
    """Get user-editable preferences for a profile."""
    return settings_service.get_profile_preferences(name)


@router.put("/profiles/{name}/preferences", response_model=ProfilePreferencesResponse)
async def update_profile_preferences(name: str, prefs: ProfilePreferences):
    """Update user-editable preferences for a profile."""
    try:
        return settings_service.update_profile_preferences(name, prefs.model_dump())
    except Exception as e:
        logger.exception("Failed to update profile preferences")
        raise HTTPException(500, detail=str(e))
