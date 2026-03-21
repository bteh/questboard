"""Settings and configuration endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.schemas.settings import (
    DatabaseInfo,
    FetchModelsRequest,
    LLMConfig,
    LLMStatus,
    LLMTestResult,
    LocalAIDetectResult,
    OllamaDetectResult,
    ProfileDetail,
    ProfilePreferences,
    ProfilePreferencesResponse,
    ProfileSummary,
    ProviderModel,
    ProviderPreset,
)
from app.services import settings_service
from app.dependencies import sanitize_profile
from app.models.database import get_db
from app.services import workspace_service
from app.config import get_settings

router = APIRouter(tags=["settings"])


# --- LLM Configuration ---


@router.get("/settings/llm", response_model=LLMStatus)
async def get_llm_config(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get current LLM configuration and connection status."""
    import asyncio

    workspace = workspace_service.get_workspace_context_optional(db, request)
    if workspace and get_settings().hosted_mode:
        return workspace_service.get_workspace_llm_status(db, workspace.workspace.id)
    return await asyncio.to_thread(settings_service.get_llm_status)


@router.put("/settings/llm", response_model=LLMStatus)
async def update_llm_config(
    config: LLMConfig,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update LLM provider configuration."""
    base = config.base_url.rstrip("/")
    if base and not _is_safe_url(base):
        raise HTTPException(
            400,
            "Invalid base_url: must use https:// or http://localhost / http://127.0.0.1",
        )
    workspace = workspace_service.get_workspace_context_optional(db, request)
    if workspace and get_settings().hosted_mode:
        workspace = workspace_service.require_workspace_context(db, request, validate_csrf=True)
        return workspace_service.save_workspace_llm_config(
            db,
            workspace.workspace.id,
            provider=config.provider,
            base_url=base,
            api_key=config.api_key,
            model=config.model,
        )
    if not settings_service.runtime_llm_config_allowed():
        raise HTTPException(403, detail="Runtime LLM configuration is disabled")
    try:
        return settings_service.update_llm_config(
            provider=config.provider,
            base_url=base,
            api_key=config.api_key,
            model=config.model,
        )
    except Exception as e:
        logger.exception("Failed to update LLM config")
        raise HTTPException(500, detail=str(e))


@router.get("/settings/llm/detect-ollama", response_model=OllamaDetectResult)
async def detect_ollama():
    """Probe localhost for Ollama and return available models."""
    import asyncio

    return await asyncio.to_thread(settings_service.detect_ollama)


@router.get("/settings/llm/detect-local", response_model=LocalAIDetectResult)
async def detect_local_ai():
    """Scan common localhost ports for OpenAI-compatible AI servers."""
    import asyncio

    return await asyncio.to_thread(settings_service.detect_local_ai)


@router.post("/settings/llm/test", response_model=LLMTestResult)
async def test_llm_connection(
    request: Request,
    db: Session = Depends(get_db),
):
    """Test the current LLM connection."""
    workspace = workspace_service.get_workspace_context_optional(db, request)
    if workspace and get_settings().hosted_mode:
        return workspace_service.test_workspace_llm_connection(db, workspace.workspace.id)
    return settings_service.test_llm_connection()


def _is_safe_url(url: str) -> bool:
    """Validate that a URL is safe to proxy requests to.

    Allows https:// URLs and localhost/127.0.0.1 over http://.
    Rejects all other http:// targets to prevent SSRF against internal services.
    """
    from urllib.parse import urlparse
    import ipaddress

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme == "https":
        # Reject if the hostname resolves to a private/internal IP
        hostname = parsed.hostname or ""
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                return False
        except ValueError:
            # Not a raw IP — it's a hostname, which is fine for https
            pass
        return True

    if parsed.scheme == "http":
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        return False

    return False


@router.post("/settings/llm/models", response_model=list[ProviderModel])
async def fetch_provider_models(req: FetchModelsRequest):
    """Fetch available models from a provider's /models endpoint.

    Proxies the request so the frontend doesn't need CORS access to
    arbitrary provider URLs.
    """
    import requests as http_requests

    if not settings_service.runtime_llm_config_allowed() and not get_settings().hosted_mode:
        raise HTTPException(403, detail="Runtime LLM configuration is disabled")

    base = req.base_url.rstrip("/")

    if not _is_safe_url(base):
        raise HTTPException(
            400,
            "Invalid base_url: must use https:// or http://localhost / http://127.0.0.1",
        )

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
    name = sanitize_profile(name)
    return settings_service.get_profile_preferences(name)


@router.put("/profiles/{name}/preferences", response_model=ProfilePreferencesResponse)
async def update_profile_preferences(name: str, prefs: ProfilePreferences):
    """Update user-editable preferences for a profile."""
    name = sanitize_profile(name)
    try:
        return settings_service.update_profile_preferences(
            name,
            prefs.model_dump(exclude_unset=True),
        )
    except Exception as e:
        logger.exception("Failed to update profile preferences")
        raise HTTPException(500, detail=str(e))
