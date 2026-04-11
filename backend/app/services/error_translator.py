"""Translate technical LLM/network errors into plain-language messages with actions.

Single source of truth for error-to-user-message mapping. Both the status
endpoints and the frontend consume this via the translated payload that
includes: code, title, message, and a next_action dict that tells the UI
how to help the user recover.

Taxonomy:
  invalid_key       — 401/403, bad api key format, "unauthorized"
  quota_exceeded    — 429 with daily/project quota language
  rate_limited      — 429 transient (retry-after, per-minute)
  proxy_expired     — consumer subscription proxy auth failed
  network           — ConnectionError, DNS, timeout before response
  provider_down     — 5xx upstream errors
  model_not_found   — 404 model, "model not found", unknown model id
  ollama_not_running — connection refused on 11434
  unknown           — fallback
"""

from __future__ import annotations

import re


NextAction = dict[str, str]
Translation = dict[str, object]


def _action(kind: str, label: str, **kwargs: str) -> NextAction:
    action: NextAction = {"kind": kind, "label": label}
    action.update(kwargs)
    return action


def _make(code: str, title: str, message: str, action: NextAction) -> Translation:
    return {
        "code": code,
        "title": title,
        "message": message,
        "next_action": action,
    }


def translate(raw: Exception | str | None, *, provider: str = "") -> Translation:
    """Convert a raw exception or error string into a plain-language payload.

    Args:
        raw: An exception object, a string, or None.
        provider: The provider name (gemini, groq, etc.) for context-aware messaging.

    Returns:
        Translation dict with code, title, message, next_action.
    """
    if raw is None:
        return _unknown_translation(provider)

    text = str(raw) if not isinstance(raw, str) else raw
    lowered = text.lower()

    pretty_provider = _pretty_provider(provider)

    # ── Ollama not running ────────────────────────────────────────────
    if "11434" in text and ("refused" in lowered or "connection" in lowered):
        return _make(
            "ollama_not_running",
            "Ollama is not running",
            "Your local AI engine isn't running. Start Ollama or use Quick Start to install it.",
            _action("open_quick_start", "Set up Local AI"),
        )

    # ── Auth / invalid key ────────────────────────────────────────────
    if any(term in lowered for term in ("401", "invalid api key", "invalid_api_key", "invalid authentication", "unauthorized")):
        return _make(
            "invalid_key",
            f"{pretty_provider} API key is invalid",
            f"The API key you entered for {pretty_provider} was rejected. It may be expired or copied incorrectly.",
            _action("reconnect", "Re-enter key", provider=provider),
        )

    # ── Forbidden / permission ────────────────────────────────────────
    if "403" in text or "permission" in lowered or "forbidden" in lowered:
        return _make(
            "invalid_key",
            f"{pretty_provider} denied the request",
            f"{pretty_provider} rejected the request. Your key may not have permission for this model.",
            _action("reconnect", "Check key & model", provider=provider),
        )

    # ── Consumer proxy auth ───────────────────────────────────────────
    if "auth_unavailable" in lowered or ("proxy" in lowered and "auth" in lowered):
        return _make(
            "proxy_expired",
            "Subscription proxy session expired",
            "Your Claude/ChatGPT subscription proxy needs to be re-authenticated. This is a limitation of consumer proxies — free Gemini/Groq keys are more reliable.",
            _action("switch_provider", "Switch to free Gemini"),
        )

    # ── Quota exceeded (daily/project) ────────────────────────────────
    if "429" in text and any(term in lowered for term in ("quota", "daily", "free_tier", "resource_exhausted", "generate_content_free_tier")):
        return _make(
            "quota_exceeded",
            f"{pretty_provider} daily limit reached",
            f"You've used up today's free quota on {pretty_provider}. Quota resets tomorrow, or switch to another provider.",
            _action("switch_provider", "Switch to Groq (14,400/day)"),
        )

    # ── Rate limited (transient) ──────────────────────────────────────
    if "429" in text or "rate limit" in lowered or "too many requests" in lowered:
        return _make(
            "rate_limited",
            "Rate limited",
            f"{pretty_provider} is temporarily throttling requests. Wait a moment and try again.",
            _action("retry", "Try again"),
        )

    # ── Model not found ───────────────────────────────────────────────
    if "model" in lowered and ("not found" in lowered or "not_found" in lowered or "unknown" in lowered or "404" in text):
        return _make(
            "model_not_found",
            "Model not found",
            f"The model isn't available on {pretty_provider}. Pick a different model in Settings → AI.",
            _action("open_settings", "Open Settings"),
        )

    # ── Provider down (5xx) ───────────────────────────────────────────
    if re.search(r"\b5\d\d\b", text) or "internal server error" in lowered or "bad gateway" in lowered:
        return _make(
            "provider_down",
            f"{pretty_provider} is having issues",
            f"{pretty_provider}'s servers returned an error. This usually resolves in a few minutes.",
            _action("retry", "Try again"),
        )

    # ── Network / timeout ─────────────────────────────────────────────
    if any(term in lowered for term in ("timeout", "timed out", "connection error", "connection refused", "network", "dns", "name resolution", "unreachable")):
        return _make(
            "network",
            "Can't reach AI provider",
            f"Could not connect to {pretty_provider}. Check your internet connection.",
            _action("retry", "Try again"),
        )

    # ── Unknown fallback ──────────────────────────────────────────────
    return _unknown_translation(provider, detail=text[:200])


def _unknown_translation(provider: str, detail: str = "") -> Translation:
    pretty = _pretty_provider(provider)
    message = f"Something went wrong connecting to {pretty}."
    if detail:
        message = f"{message} Details: {detail}"
    return _make(
        "unknown",
        "AI connection issue",
        message,
        _action("open_diagnostic", "Run diagnostics"),
    )


def _pretty_provider(provider: str) -> str:
    mapping = {
        "gemini": "Gemini",
        "groq": "Groq",
        "openai-api": "OpenAI",
        "anthropic-api": "Anthropic Claude",
        "ollama": "Ollama",
        "claude-proxy": "Claude subscription proxy",
        "openai-proxy": "ChatGPT subscription proxy",
        "": "your AI provider",
    }
    return mapping.get(provider, provider or "your AI provider")
