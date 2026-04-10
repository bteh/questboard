"""Settings service — .env management, profile reading, LLM testing."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.config import get_settings
from app.dependencies import get_llm, get_config

logger = logging.getLogger(__name__)


def _sanitize_error(msg: str, api_key: str | None = None) -> str:
    """Remove API keys, tokens, and auth headers from error messages."""
    import re

    if api_key and len(api_key) > 4:
        msg = msg.replace(api_key, "***")
    # Redact Bearer tokens
    msg = re.sub(r"Bearer\s+\S+", "Bearer ***", msg)
    # Redact common key patterns (sk-..., AIza..., gsk_..., etc.)
    msg = re.sub(r"\b(sk-|AIza|gsk_|xai-|key-)\S+", "***", msg)
    return msg


def _normalize_level(val: str | list | None) -> str:
    """Normalize legacy list-based level values to a single string."""
    if isinstance(val, list):
        for item in val:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return "mid"
    if isinstance(val, str) and val.strip():
        return val.strip()
    return "mid"


def _clean_string_list(values: list | None) -> list[str]:
    """Return only non-empty strings from a list-like value."""
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value.strip()]


def _clean_location_list(values: list | None) -> list[str]:
    """Return de-duplicated non-remote location strings."""
    raw_values = _clean_string_list(values)
    merged_values: list[str] = []
    i = 0
    while i < len(raw_values):
        current = raw_values[i].strip()
        nxt = raw_values[i + 1].strip() if i + 1 < len(raw_values) else ""
        if (
            current
            and nxt
            and "," not in current
            and len(nxt) == 2
            and nxt.isalpha()
        ):
            merged_values.append(f"{current}, {nxt.upper()}")
            i += 2
            continue
        merged_values.append(current)
        i += 1

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in merged_values:
        lowered = value.strip().lower()
        if lowered in {"remote", "anywhere", "united states", "usa", "us"}:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value.strip())
    return cleaned


def _derive_workplace_preference(cfg: dict) -> str:
    """Infer the saved workplace preference from config."""
    loc_prefs = cfg.get("location_preferences", {})
    stored = loc_prefs.get("workplace_preference")
    if stored in {"remote_friendly", "remote_only", "location_only"}:
        return stored
    if loc_prefs.get("remote_only", False):
        return "remote_only"
    if "include_remote" in loc_prefs:
        return "remote_friendly" if loc_prefs.get("include_remote", True) else "location_only"

    locations = [value.lower() for value in _clean_string_list(cfg.get("locations"))]
    return "remote_friendly" if "remote" in locations else "location_only"


def _extract_preferred_locations(cfg: dict) -> list[str]:
    """Return saved non-remote preferred locations."""
    loc_prefs = cfg.get("location_preferences", {})
    preferred_locations = _clean_location_list(loc_prefs.get("preferred_locations"))
    if preferred_locations:
        return preferred_locations
    return _clean_location_list(cfg.get("locations"))


def _build_location_settings(
    preferred_locations: list[str],
    workplace_preference: str,
) -> tuple[list[str], dict]:
    """Convert UI work preferences into config fields."""
    from job_finder.company_classifier import parse_location

    cleaned_locations = _clean_location_list(preferred_locations)
    include_remote = workplace_preference != "location_only"
    remote_only = workplace_preference == "remote_only"

    preferred_states: list[str] = []
    preferred_cities: list[str] = []
    for location in cleaned_locations:
        parsed = parse_location(location)
        if parsed.get("state") and parsed["state"] not in preferred_states:
            preferred_states.append(parsed["state"])
        if parsed.get("city") and parsed["city"] not in preferred_cities:
            preferred_cities.append(parsed["city"])

    effective_locations = list(cleaned_locations)
    if remote_only:
        effective_locations = ["Remote"]
    elif include_remote:
        effective_locations.append("Remote")

    return effective_locations, {
        "filter_enabled": bool(cleaned_locations) or remote_only or not include_remote,
        "preferred_locations": cleaned_locations,
        "preferred_states": preferred_states,
        "preferred_cities": preferred_cities,
        "remote_only": remote_only,
        "include_remote": include_remote,
        "workplace_preference": workplace_preference,
    }

# Resolve project root (backend/../)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


def detect_ollama() -> dict:
    """Probe Ollama at localhost:11434 and return detection results."""
    import requests as http_requests

    result = {"detected": False, "models": [], "recommended_model": ""}
    try:
        resp = http_requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code != 200:
            return result
        data = resp.json()
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        if not models:
            return result
        result["detected"] = True
        result["models"] = models
        # Pick the best available model (prefer the one we install by default)
        preferred = ["llama3.2:3b", "llama3.2", "llama3.1", "llama3", "mistral", "gemma2", "qwen2.5"]
        for pref in preferred:
            for m in models:
                if m.startswith(pref):
                    result["recommended_model"] = m
                    return result
        # Fallback to first model
        result["recommended_model"] = models[0]
    except Exception:
        pass
    return result


def detect_local_ai() -> dict:
    """Scan common localhost ports for OpenAI-compatible servers.

    We deliberately scan ONLY ports used by real local AI runtimes (LM Studio
    and a couple of generic local-AI defaults). Ollama has its own dedicated
    detection in detect_ollama() and is excluded here.

    We previously also scanned 8317, 8741, and 3456 — the default ports for
    cliproxyapi-style "wrap your Claude Code / Codex CLI / Gemini CLI OAuth
    subscription as an OpenAI-compatible local server" tools. Those tools
    re-export vendor flagship model IDs (claude-*, gpt-*, gemini-*) as if
    they were a local runtime, but in reality they bill against the user's
    consumer subscription quota — and using those quotas to power a backend
    job-scoring loop violates Anthropic / OpenAI / Google's terms of service.
    Auto-discovering them as a "click to connect" provider risked promoting
    that gray area to mainstream users who couldn't tell what they were
    actually wiring up.

    Power users running cliproxyapi (or anything else exposing custom model
    IDs) can still wire it up by hand via the Custom Provider section in the
    advanced AI settings.
    """
    import requests as http_requests

    SCAN_PORTS = [
        (1234, "LM Studio"),
        (5001, "Local AI"),
        (4000, "Local AI"),
    ]

    servers: list[dict] = []
    for port, label in SCAN_PORTS:
        base_url = f"http://localhost:{port}/v1"
        try:
            resp = http_requests.get(f"{base_url}/models", timeout=1.5)
            if resp.status_code != 200:
                continue
            data = resp.json()
            models_list = data.get("data", [])
            model_ids = [m.get("id", "") for m in models_list if m.get("id")]
            if not model_ids:
                continue
            servers.append({
                "port": port,
                "base_url": base_url,
                "model": model_ids[0],
                "models": model_ids[:10],
                "label": label or f"AI server (port {port})",
            })
        except Exception:
            continue

    return {"servers": servers}


def _auto_detect_and_configure() -> str:
    """If no LLM is configured, try to auto-detect Ollama and configure it.

    Returns the auto-detected provider name, or empty string if none.
    """
    detection = detect_ollama()
    if not detection["detected"] or not detection["recommended_model"]:
        return ""
    model = detection["recommended_model"]
    logger.info("Auto-detected Ollama with model %s — configuring automatically", model)
    _write_env_vars({
        "LLM_PROVIDER": "ollama",
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "LLM_MODEL": model,
        "LLM_AUTO_DETECTED": "ollama",
    })
    # Ollama doesn't need a real API key
    os.environ["LLM_API_KEY"] = "ollama"
    return "ollama"


def get_llm_status() -> dict:
    """Return current LLM configuration and availability."""
    from job_finder.secrets import is_available as keyring_available

    auto_detected = os.getenv("LLM_AUTO_DETECTED", "")
    # If no provider is configured, try auto-detecting Ollama
    if not os.getenv("LLM_PROVIDER"):
        auto_detected = _auto_detect_and_configure()

    llm = get_llm()
    info = llm.get_provider_info()
    available = False
    if llm.is_configured:
        try:
            available = llm.is_available()
        except Exception:
            pass
    return {
        "configured": llm.is_configured,
        "available": available,
        "provider": os.getenv("LLM_PROVIDER", ""),
        "model": info.get("model", ""),
        "label": info.get("label", ""),
        "runtime_configurable": bool(get_settings().allow_runtime_llm_config),
        "key_storage": "keychain" if keyring_available() else "local_file",
        "auto_detected": auto_detected,
    }


def runtime_llm_config_allowed() -> bool:
    return bool(get_settings().allow_runtime_llm_config)


def _remove_env_var(key: str) -> None:
    """Remove a key from .env if it exists."""
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            line_key = stripped.split("=", 1)[0].strip()
            if line_key == key:
                continue
        new_lines.append(line)
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _write_env_vars(env_vars: dict[str, str]) -> None:
    """Write key=value pairs to .env, updating existing or appending."""
    lines: list[str] = []
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in env_vars:
                new_lines.append(f"{key}={env_vars[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, value in env_vars.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    for key, value in env_vars.items():
        os.environ[key] = value


def update_llm_config(provider: str, base_url: str, api_key: str, model: str) -> dict:
    """Store LLM config — API key goes to OS keychain, rest to .env."""
    from job_finder.secrets import store_secret, is_available as keyring_available

    # Clear auto-detected flag when user explicitly configures a provider
    _remove_env_var("LLM_AUTO_DETECTED")
    os.environ.pop("LLM_AUTO_DETECTED", None)

    # Non-sensitive config → .env
    _write_env_vars({
        "LLM_PROVIDER": provider,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    })

    # API key → OS keychain (falls back to .env if keychain unavailable)
    if api_key:
        if keyring_available() and store_secret("llm_api_key", api_key):
            # Remove plaintext key from .env if it exists
            _remove_env_var("LLM_API_KEY")
            os.environ["LLM_API_KEY"] = api_key
            logger.info("API key stored in OS keychain")
        else:
            _write_env_vars({"LLM_API_KEY": api_key})
            logger.info("API key stored in .env (keychain unavailable)")

    # Clear stale suggest/profile caches so the new provider gets a fresh run
    _flush_llm_caches()

    return get_llm_status()


def _flush_llm_caches() -> None:
    """Clear in-memory LLM result caches when the provider changes."""
    try:
        from app.api.search import _suggest_cache
        _suggest_cache.clear()
    except Exception:
        pass
    try:
        from app.api.onboarding import _GENERATED_PROFILE_CACHE
        _GENERATED_PROFILE_CACHE.clear()
    except Exception:
        pass


def test_llm_connection() -> dict:
    """Test current LLM configuration."""
    llm = get_llm()
    if not llm.is_configured:
        return {
            "success": False,
            "provider": "",
            "model": "",
            "message": "No LLM provider configured",
        }
    info = llm.get_provider_info()
    try:
        available = llm.is_available()
    except Exception as e:
        # Sanitize error message — never leak API keys or auth headers
        raw_msg = str(e)
        safe_msg = _sanitize_error(raw_msg, llm.api_key)
        logger.debug("LLM connection test failed: %s", raw_msg)
        return {
            "success": False,
            "provider": os.getenv("LLM_PROVIDER", ""),
            "model": info.get("model", ""),
            "message": f"Connection failed: {safe_msg}",
        }
    return {
        "success": available,
        "provider": os.getenv("LLM_PROVIDER", ""),
        "model": info.get("model", ""),
        "message": "Connected successfully" if available else "Failed to reach LLM endpoint",
    }


def get_provider_presets(include_internal: bool = False) -> list[dict]:
    """Return available LLM provider presets.

    Internal/proxy presets are hidden by default unless *include_internal* is True.
    """
    from job_finder.llm_client import PRESETS

    results = []
    for name, preset in PRESETS.items():
        if preset.get("internal") == "true" and not include_internal:
            continue
        results.append({
            "name": name,
            "label": preset.get("label", name),
            "base_url": preset.get("base_url", ""),
            "model": preset.get("model", ""),
            "needs_api_key": preset.get("needs_api_key") == "true",
            "internal": preset.get("internal") == "true",
        })
    return results


def list_profiles() -> list[dict]:
    """List available profile YAML files."""
    config_dir = os.path.join(_PROJECT_ROOT, "src", "job_finder", "config", "profiles")
    default_cfg = get_config(None)
    default_info = default_cfg.get("profile", {})
    profiles = [{
        "name": "default",
        "display_name": default_info.get("name", "Default"),
        "description": default_info.get("description", "Starter profile"),
        "target_roles_count": len(_clean_string_list(default_cfg.get("target_roles"))),
        "locations": default_cfg.get("locations", []),
    }]

    if os.path.isdir(config_dir):
        for fname in sorted(os.listdir(config_dir)):
            if fname.endswith(".yaml") and not fname.startswith("_"):
                name = fname.replace(".yaml", "")
                if name == "default":
                    continue
                cfg = get_config(name)
                profile_info = cfg.get("profile", {})
                profiles.append({
                    "name": name,
                    "display_name": profile_info.get("name", name.title()),
                    "description": profile_info.get("description", ""),
                    "target_roles_count": len(_clean_string_list(cfg.get("target_roles"))),
                    "locations": cfg.get("locations", []),
                })
    return profiles


def get_profile_detail(name: str) -> dict | None:
    """Return full config for a profile."""
    cfg = get_config(name if name != "default" else None)
    if not cfg:
        return None
    return {"name": name, "config": cfg}


def get_profile_preferences(name: str) -> dict:
    """Extract the user-editable preferences from a profile config."""
    cfg = get_config(name if name != "default" else None)
    career = cfg.get("career_baseline", {})
    comp = cfg.get("compensation", {})
    auto = cfg.get("auto_apply", {})
    scoring = cfg.get("scoring", {})
    thresholds = scoring.get("thresholds", {})
    search = cfg.get("search_settings", {})
    return {
        "name": name,
        "preferences": {
            "preferred_locations": _extract_preferred_locations(cfg),
            "workplace_preference": _derive_workplace_preference(cfg),
            "max_days_old": search.get("max_days_old", 14),
            "current_title": career.get("current_title", ""),
            "current_level": _normalize_level(career.get("current_level", "mid")),
            "current_tc": career.get("current_tc", 100_000),
            "min_base": comp.get("min_base", 80_000),
            "target_total_comp": comp.get("target_total_comp", 150_000),
            "auto_apply_enabled": auto.get("enabled", False),
            "auto_apply_dry_run": auto.get("dry_run", True),
            # Scoring weights
            "scoring_technical": scoring.get("technical_skills", 0.25),
            "scoring_leadership": scoring.get("leadership_signal", 0.15),
            "scoring_career_progression": scoring.get("career_progression", 0.15),
            "scoring_platform": scoring.get("platform_building", 0.13),
            "scoring_comp": scoring.get("comp_potential", 0.12),
            "scoring_trajectory": scoring.get("company_trajectory", 0.10),
            "scoring_culture": scoring.get("culture_fit", 0.10),
            # Thresholds
            "threshold_strong_apply": thresholds.get("strong_apply", 70),
            "threshold_apply": thresholds.get("apply", 55),
            "threshold_maybe": thresholds.get("maybe", 40),
            # Toggles
            "exclude_staffing_agencies": search.get("exclude_staffing_agencies", True),
            "include_equity": comp.get("include_equity", True),
            # Career
            "min_acceptable_tc": career.get("min_acceptable_tc"),
        },
    }


def _extract_prefs_from_config(cfg: dict) -> dict:
    """Extract the flat preference dict from a nested profile config."""
    career = cfg.get("career_baseline", {})
    comp = cfg.get("compensation", {})
    auto = cfg.get("auto_apply", {})
    scoring = cfg.get("scoring", {})
    thresholds = scoring.get("thresholds", {})
    search = cfg.get("search_settings", {})
    result: dict = {
        "preferred_locations": _extract_preferred_locations(cfg),
        "workplace_preference": _derive_workplace_preference(cfg),
        "max_days_old": search.get("max_days_old", 14),
        "current_title": career.get("current_title", ""),
        "current_level": _normalize_level(career.get("current_level", "mid")),
        "current_tc": career.get("current_tc", 100_000),
        "min_base": comp.get("min_base", 80_000),
        "target_total_comp": comp.get("target_total_comp", 150_000),
    }
    # Include auto_apply fields if present
    if "enabled" in auto:
        result["auto_apply_enabled"] = auto["enabled"]
    if "dry_run" in auto:
        result["auto_apply_dry_run"] = auto["dry_run"]
    # Scoring weights
    result["scoring_technical"] = scoring.get("technical_skills", 0.25)
    result["scoring_leadership"] = scoring.get("leadership_signal", 0.15)
    result["scoring_career_progression"] = scoring.get("career_progression", 0.15)
    result["scoring_platform"] = scoring.get("platform_building", 0.13)
    result["scoring_comp"] = scoring.get("comp_potential", 0.12)
    result["scoring_trajectory"] = scoring.get("company_trajectory", 0.10)
    result["scoring_culture"] = scoring.get("culture_fit", 0.10)
    # Thresholds
    result["threshold_strong_apply"] = thresholds.get("strong_apply", 70)
    result["threshold_apply"] = thresholds.get("apply", 55)
    result["threshold_maybe"] = thresholds.get("maybe", 40)
    # Toggles
    result["exclude_staffing_agencies"] = search.get("exclude_staffing_agencies", True)
    result["include_equity"] = comp.get("include_equity", True)
    # Career
    result["min_acceptable_tc"] = career.get("min_acceptable_tc")
    return result


def _compute_settings_diff(old: dict, new: dict) -> dict:
    """Compute a diff of changed fields between old and new preference dicts.

    Returns a dict mapping field names to ``{"old": ..., "new": ...}`` pairs.
    Only fields that actually changed are included.
    """
    changes: dict = {}
    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


def _write_audit_entry(profile: str, changes: dict) -> None:
    """Append a JSON-lines entry to data/settings_audit.log."""
    data_dir = os.path.join(_PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    audit_path = os.path.join(data_dir, "settings_audit.log")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "changes": changes,
    }
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def update_profile_preferences(name: str, prefs: dict) -> dict:
    """Update the user-editable preferences in a profile YAML file.

    Creates the profile from the template if it doesn't exist yet.
    Logs a diff of what changed and writes an audit trail entry.
    """
    import yaml

    config_dir = os.path.join(_PROJECT_ROOT, "src", "job_finder", "config", "profiles")
    os.makedirs(config_dir, exist_ok=True)

    profile_name = name if name != "default" else "default"
    profile_path = os.path.join(config_dir, f"{profile_name}.yaml")
    template_path = os.path.join(config_dir, "_template.yaml")

    # Load existing config or copy from template
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    elif os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    # Snapshot old preferences before mutation
    old_prefs = _extract_prefs_from_config(cfg)

    # Update career_baseline
    if "career_baseline" not in cfg:
        cfg["career_baseline"] = {}
    if prefs.get("current_title"):
        cfg["career_baseline"]["current_title"] = prefs["current_title"]
    if prefs.get("current_level"):
        cfg["career_baseline"]["current_level"] = _normalize_level(prefs["current_level"])
    if prefs.get("current_tc") is not None:
        cfg["career_baseline"]["current_tc"] = prefs["current_tc"]

    # Update compensation
    if "compensation" not in cfg:
        cfg["compensation"] = {}
    if prefs.get("min_base") is not None:
        cfg["compensation"]["min_base"] = prefs["min_base"]
    if prefs.get("target_total_comp") is not None:
        cfg["compensation"]["target_total_comp"] = prefs["target_total_comp"]

    # Update auto_apply settings if provided
    if "auto_apply_enabled" in prefs or "auto_apply_dry_run" in prefs:
        if "auto_apply" not in cfg:
            cfg["auto_apply"] = {}
        if "auto_apply_enabled" in prefs:
            cfg["auto_apply"]["enabled"] = prefs["auto_apply_enabled"]
        if "auto_apply_dry_run" in prefs:
            cfg["auto_apply"]["dry_run"] = prefs["auto_apply_dry_run"]

    # Update scoring weights
    scoring_keys = {
        "scoring_technical": "technical_skills",
        "scoring_leadership": "leadership_signal",
        "scoring_career_progression": "career_progression",
        "scoring_platform": "platform_building",
        "scoring_comp": "comp_potential",
        "scoring_trajectory": "company_trajectory",
        "scoring_culture": "culture_fit",
    }
    has_scoring = any(k in prefs for k in scoring_keys)
    if has_scoring:
        if "scoring" not in cfg:
            cfg["scoring"] = {}
        for pref_key, yaml_key in scoring_keys.items():
            if pref_key in prefs:
                cfg["scoring"][yaml_key] = prefs[pref_key]

    # Update thresholds
    threshold_keys = {
        "threshold_strong_apply": "strong_apply",
        "threshold_apply": "apply",
        "threshold_maybe": "maybe",
    }
    has_thresholds = any(k in prefs for k in threshold_keys)
    if has_thresholds:
        if "scoring" not in cfg:
            cfg["scoring"] = {}
        if "thresholds" not in cfg["scoring"]:
            cfg["scoring"]["thresholds"] = {}
        for pref_key, yaml_key in threshold_keys.items():
            if pref_key in prefs:
                cfg["scoring"]["thresholds"][yaml_key] = prefs[pref_key]

    # Update toggles
    if "exclude_staffing_agencies" in prefs:
        if "search_settings" not in cfg:
            cfg["search_settings"] = {}
        cfg["search_settings"]["exclude_staffing_agencies"] = prefs["exclude_staffing_agencies"]

    if "max_days_old" in prefs:
        if "search_settings" not in cfg:
            cfg["search_settings"] = {}
        cfg["search_settings"]["max_days_old"] = prefs["max_days_old"]

    if "include_equity" in prefs:
        if "compensation" not in cfg:
            cfg["compensation"] = {}
        cfg["compensation"]["include_equity"] = prefs["include_equity"]

    # Update min_acceptable_tc
    if "min_acceptable_tc" in prefs:
        if "career_baseline" not in cfg:
            cfg["career_baseline"] = {}
        if prefs["min_acceptable_tc"] is not None:
            cfg["career_baseline"]["min_acceptable_tc"] = prefs["min_acceptable_tc"]
        elif "min_acceptable_tc" in cfg["career_baseline"]:
            del cfg["career_baseline"]["min_acceptable_tc"]

    if "preferred_locations" in prefs or "workplace_preference" in prefs:
        preferred_locations = prefs.get("preferred_locations")
        if preferred_locations is None:
            preferred_locations = _extract_preferred_locations(cfg)

        workplace_preference = prefs.get("workplace_preference")
        if workplace_preference not in {"remote_friendly", "remote_only", "location_only"}:
            workplace_preference = _derive_workplace_preference(cfg)

        effective_locations, location_settings = _build_location_settings(
            preferred_locations,
            workplace_preference,
        )
        cfg["locations"] = effective_locations
        cfg["location_preferences"] = location_settings

    # Write back
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Compute diff and log/audit
    new_prefs = _extract_prefs_from_config(cfg)
    changes = _compute_settings_diff(old_prefs, new_prefs)
    if changes:
        logger.info("Settings changed for profile '%s': %s", name, changes)
        _write_audit_entry(name, changes)

    return get_profile_preferences(name)


def get_database_info() -> dict:
    """Return database path, size, and record count."""
    from app.models.database import get_db, init_db

    db_path = os.path.join(_PROJECT_ROOT, "data", "job_tracker.db")
    exists = os.path.exists(db_path)
    size_mb = 0.0
    record_count = 0

    if exists:
        size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        try:
            # Use a fresh session to count
            from sqlalchemy import func
            from app.models.application import ApplicationRecord

            init_db(db_path)
            gen = get_db()
            db = next(gen)
            try:
                record_count = db.query(func.count(ApplicationRecord.id)).scalar() or 0
            finally:
                try:
                    next(gen)
                except StopIteration:
                    pass
        except Exception:
            pass

    return {
        "path": db_path,
        "exists": exists,
        "size_mb": size_mb,
        "record_count": record_count,
    }
