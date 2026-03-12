"""Settings service — .env management, profile reading, LLM testing."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.dependencies import get_llm, get_config

logger = logging.getLogger(__name__)


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
    auto = cfg.get("auto_apply", {})
    scoring = cfg.get("scoring", {})
    thresholds = scoring.get("thresholds", {})
    search = cfg.get("search_settings", {})
    return {
        "name": name,
        "preferences": {
            "current_title": career.get("current_title", ""),
            "current_level": _ensure_list(career.get("current_level", ["mid"])),
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
        "current_title": career.get("current_title", ""),
        "current_level": _ensure_list(career.get("current_level", ["mid"])),
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

