"""Settings service — .env management, profile reading, LLM testing."""

from __future__ import annotations

import os

from app.dependencies import get_llm, get_config


def _ensure_list(val: str | list) -> list[str]:
    """Normalize legacy single-string values to a list."""
    if isinstance(val, list):
        return val
    return [val] if val else ["mid"]

# Resolve project root (backend/../)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


def get_llm_status() -> dict:
    """Return current LLM configuration and availability."""
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
    }


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
    """Write LLM config to .env and return updated status."""
    _write_env_vars({
        "LLM_PROVIDER": provider,
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": api_key,
        "LLM_MODEL": model,
    })
    return get_llm_status()


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
        return {
            "success": False,
            "provider": os.getenv("LLM_PROVIDER", ""),
            "model": info.get("model", ""),
            "message": f"Connection failed: {e}",
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
    profiles = [{"name": "default", "display_name": "Default", "description": "Default search config"}]

    if os.path.isdir(config_dir):
        import yaml

        for fname in sorted(os.listdir(config_dir)):
            if fname.endswith(".yaml") and not fname.startswith("_"):
                name = fname.replace(".yaml", "")
                cfg = get_config(name)
                profile_info = cfg.get("profile", {})
                profiles.append({
                    "name": name,
                    "display_name": profile_info.get("name", name.title()),
                    "description": profile_info.get("description", ""),
                    "target_roles_count": len(cfg.get("target_roles", [])),
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
    return {
        "name": name,
        "preferences": {
            "current_title": career.get("current_title", ""),
            "current_level": _ensure_list(career.get("current_level", ["mid"])),
            "current_tc": career.get("current_tc", 100_000),
            "min_base": comp.get("min_base", 80_000),
            "target_total_comp": comp.get("target_total_comp", 150_000),
        },
    }


def update_profile_preferences(name: str, prefs: dict) -> dict:
    """Update the user-editable preferences in a profile YAML file.

    Creates the profile from the template if it doesn't exist yet.
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

    # Update career_baseline
    if "career_baseline" not in cfg:
        cfg["career_baseline"] = {}
    if prefs.get("current_title"):
        cfg["career_baseline"]["current_title"] = prefs["current_title"]
    if prefs.get("current_level"):
        cfg["career_baseline"]["current_level"] = prefs["current_level"]
    if prefs.get("current_tc") is not None:
        cfg["career_baseline"]["current_tc"] = prefs["current_tc"]

    # Update compensation
    if "compensation" not in cfg:
        cfg["compensation"] = {}
    if prefs.get("min_base") is not None:
        cfg["compensation"]["min_base"] = prefs["min_base"]
    if prefs.get("target_total_comp") is not None:
        cfg["compensation"]["target_total_comp"] = prefs["target_total_comp"]

    # Write back
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

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

