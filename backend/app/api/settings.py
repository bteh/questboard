"""Settings and configuration endpoints."""

from __future__ import annotations

import logging
import os

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
from app.dependencies import reject_legacy_route_in_hosted_mode, sanitize_profile
from app.models.database import get_db
from app.services import workspace_service
from app.config import get_settings

router = APIRouter(tags=["settings"])


# --- LLM Configuration ---


def _invalid_base_url_detail(*, hosted_mode: bool) -> str:
    if hosted_mode:
        return "Invalid base_url: hosted mode only allows https:// provider endpoints"
    return "Invalid base_url: must use https:// or http://localhost / http://127.0.0.1"


def _workspace_scoped_llm_mode() -> bool:
    settings = get_settings()
    return bool(
        settings.hosted_mode
        or os.environ.get("LAUNCHBOARD_DESKTOP_MODE", "").strip().lower() == "true"
    )


@router.get("/settings/llm", response_model=LLMStatus)
async def get_llm_config(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get current LLM configuration and connection status."""
    import asyncio

    if _workspace_scoped_llm_mode():
        if not get_settings().hosted_mode:
            context = workspace_service.get_workspace_context_optional(db, request)
            if not context:
                settings = get_settings()
                return {
                    "configured": False,
                    "available": False,
                    "provider": "",
                    "model": "",
                    "label": "",
                    "runtime_configurable": bool(settings.allow_workspace_llm_config),
                }
        else:
            context = workspace_service.require_workspace_context(db, request, validate_csrf=False)
        return workspace_service.get_workspace_llm_status(db, context.workspace.id)
    return await asyncio.to_thread(settings_service.get_llm_status)


@router.put("/settings/llm", response_model=LLMStatus)
async def update_llm_config(
    config: LLMConfig,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update LLM provider configuration."""
    base = config.base_url.rstrip("/")
    hosted_mode = get_settings().hosted_mode
    if base and not _is_safe_url(base, allow_local_http=not hosted_mode):
        raise HTTPException(
            400,
            _invalid_base_url_detail(hosted_mode=hosted_mode),
        )
    if _workspace_scoped_llm_mode():
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
    except ValueError as e:
        # Validation failures (bad api_key format, etc.) → 400 with clean message
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update LLM config")
        raise HTTPException(500, detail=str(e))


@router.get("/settings/llm/detect-ollama", response_model=OllamaDetectResult)
async def detect_ollama():
    """Probe localhost for Ollama and return available models."""
    reject_legacy_route_in_hosted_mode("Local AI discovery is disabled in hosted mode")
    import asyncio

    return await asyncio.to_thread(settings_service.detect_ollama)


@router.get("/settings/llm/detect-local", response_model=LocalAIDetectResult)
async def detect_local_ai():
    """Scan common localhost ports for OpenAI-compatible AI servers."""
    reject_legacy_route_in_hosted_mode("Local AI discovery is disabled in hosted mode")
    import asyncio

    return await asyncio.to_thread(settings_service.detect_local_ai)


@router.post("/settings/ollama/setup")
async def setup_ollama():
    """Kick off Ollama install + model pull in the background.

    Returns immediately with {"started": true}. The frontend polls
    /settings/ollama/setup-status for progress updates.
    Returns 409 if a setup is already running (prevents double-submit).
    """
    reject_legacy_route_in_hosted_mode("Ollama setup is not available in hosted mode")
    import threading

    if settings_service.is_ollama_setup_in_progress():
        raise HTTPException(
            status_code=409,
            detail="An Ollama setup is already running. Wait for it to finish.",
        )

    # Run in a daemon thread so the HTTP response returns immediately
    t = threading.Thread(target=settings_service.setup_ollama, daemon=True)
    t.start()
    return {"started": True}


@router.get("/settings/ollama/setup-status")
async def ollama_setup_status():
    """Poll the current Ollama setup progress."""
    reject_legacy_route_in_hosted_mode("Ollama setup is not available in hosted mode")
    return settings_service.get_ollama_setup_status()


@router.post("/settings/llm/test", response_model=LLMTestResult)
async def test_llm_connection(
    request: Request,
    db: Session = Depends(get_db),
):
    """Test the current LLM connection."""
    if _workspace_scoped_llm_mode():
        workspace = workspace_service.require_workspace_context(db, request, validate_csrf=True)
        return workspace_service.test_workspace_llm_connection(db, workspace.workspace.id)
    return settings_service.test_llm_connection()


def _is_safe_url(url: str, *, allow_local_http: bool) -> bool:
    """Validate that a URL is safe to proxy requests to.

    Allows https:// URLs and localhost/127.0.0.1 over http://.
    Rejects all other http:// targets to prevent SSRF against internal services.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    def _is_public_host(hostname: str) -> bool:
        try:
            addr = ipaddress.ip_address(hostname)
            return not (addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local)
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(hostname, None)
        except OSError:
            return False

        for info in infos:
            candidate = info[4][0]
            try:
                addr = ipaddress.ip_address(candidate)
            except ValueError:
                return False
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                return False
        return True

    if parsed.scheme == "https":
        hostname = parsed.hostname or ""
        return bool(hostname) and _is_public_host(hostname)

    if parsed.scheme == "http":
        hostname = parsed.hostname or ""
        if allow_local_http and hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        return False

    return False


@router.post("/settings/llm/models", response_model=list[ProviderModel])
async def fetch_provider_models(
    req: FetchModelsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Fetch available models from a provider's /models endpoint.

    Proxies the request so the frontend doesn't need CORS access to
    arbitrary provider URLs.
    """
    import requests as http_requests
    hosted_mode = get_settings().hosted_mode
    workspace_scoped = _workspace_scoped_llm_mode()

    if workspace_scoped:
        workspace_service.require_workspace_context(db, request, validate_csrf=True)
        if hosted_mode and not get_settings().allow_workspace_llm_config:
            raise HTTPException(403, detail="Hosted AI is platform-managed")
    elif not settings_service.runtime_llm_config_allowed():
        raise HTTPException(403, detail="Runtime LLM configuration is disabled")

    base = req.base_url.rstrip("/")

    if not _is_safe_url(base, allow_local_http=not hosted_mode):
        raise HTTPException(
            400,
            _invalid_base_url_detail(hosted_mode=hosted_mode),
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
    reject_legacy_route_in_hosted_mode("Database inspection is disabled in hosted mode")
    return settings_service.get_database_info()


# --- Profiles ---


@router.get("/profiles", response_model=list[ProfileSummary])
async def list_profiles():
    """List available search profiles."""
    reject_legacy_route_in_hosted_mode("Profile routes are disabled in hosted mode")
    return settings_service.list_profiles()


@router.get("/profiles/{name}", response_model=ProfileDetail)
async def get_profile(name: str):
    """Get full config for a profile."""
    reject_legacy_route_in_hosted_mode("Profile routes are disabled in hosted mode")
    detail = settings_service.get_profile_detail(name)
    if not detail:
        raise HTTPException(404, f"Profile '{name}' not found")
    return detail


@router.get("/profiles/{name}/preferences", response_model=ProfilePreferencesResponse)
async def get_profile_preferences(name: str):
    """Get user-editable preferences for a profile."""
    reject_legacy_route_in_hosted_mode("Profile routes are disabled in hosted mode")
    name = sanitize_profile(name)
    return settings_service.get_profile_preferences(name)


@router.put("/profiles/{name}/preferences", response_model=ProfilePreferencesResponse)
async def update_profile_preferences(name: str, prefs: ProfilePreferences):
    """Update user-editable preferences for a profile."""
    reject_legacy_route_in_hosted_mode("Profile routes are disabled in hosted mode")
    name = sanitize_profile(name)
    try:
        return settings_service.update_profile_preferences(
            name,
            prefs.model_dump(exclude_unset=True),
        )
    except Exception as e:
        logger.exception("Failed to update profile preferences")
        raise HTTPException(500, detail=str(e))
