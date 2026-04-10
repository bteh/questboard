"""Unified LLM client that works with any OpenAI-compatible endpoint.

Supports subscription proxies (CLIProxyAPI, claude-max-api-proxy),
direct APIs (Anthropic, OpenAI, Gemini), and local models (Ollama).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        first_newline = value.index("\n") if "\n" in value else 3
        value = value[first_newline + 1 :]
    if value.endswith("```"):
        value = value[:-3]
    return value.strip()


def _extract_json_candidate(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text.strip()
    end = text.rfind("}")
    if end == -1 or end < start:
        return text[start:].strip()
    return text[start : end + 1].strip()


def _close_truncated_json(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escape = False
    result: list[str] = []

    for char in text:
        result.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if stack and stack[-1] == char:
                stack.pop()

    repaired = "".join(result)
    if in_string:
        repaired += '"'
    if stack:
        repaired += "".join(reversed(stack))
    return repaired


def _parse_loose_json(text: str) -> dict | None:
    candidate = _extract_json_candidate(_strip_markdown_fences(text))
    if not candidate:
        return None

    attempts = [
        candidate,
        re.sub(r",\s*([}\]])", r"\1", candidate),
    ]

    repaired = _close_truncated_json(candidate)
    attempts.extend([
        repaired,
        re.sub(r",\s*([}\]])", r"\1", repaired),
    ])

    seen: set[str] = set()
    for attempt in attempts:
        normalized = attempt.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            value = json.loads(normalized)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    partial = _extract_partial_fields(candidate)
    if partial:
        return partial
    return None


def _extract_array_values(segment: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r'"((?:\\.|[^"\\])*)"', segment, re.DOTALL):
        try:
            values.append(json.loads(f'"{match.group(1)}"'))
        except json.JSONDecodeError:
            continue
    return values


def _extract_array_segment(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\[', text)
    if not match:
        return None

    start = match.end() - 1
    depth = 0
    in_string = False
    escape = False
    chars: list[str] = []

    for char in text[start:]:
        chars.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                break

    segment = "".join(chars).strip()
    return segment or None


def _extract_string_value(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)', text, re.DOTALL)
    if not match:
        return ""
    raw = match.group(1)
    if not raw.endswith('"'):
        raw = raw.rstrip()
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace('\\"', '"').strip()


def _extract_partial_fields(text: str) -> dict[str, Any] | None:
    extracted: dict[str, Any] = {}
    for key in ("roles", "keywords", "locations", "companies"):
        segment = _extract_array_segment(text, key)
        if not segment:
            continue
        values = _extract_array_values(segment)
        if values:
            extracted[key] = values

    summary = _extract_string_value(text, "summary")
    if summary:
        extracted["summary"] = summary

    return extracted or None


def _get_keychain_key() -> str:
    """Try to read the LLM API key from the OS keychain."""
    try:
        from job_finder.secrets import get_secret
        return get_secret("llm_api_key")
    except Exception:
        return ""


# Provider presets -------------------------------------------------------

PRESETS: dict[str, dict[str, str]] = {
    # ── Free cloud providers (recommended for public users) ──
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "api_key": "",
        "label": "Groq",
        "needs_api_key": "true",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "api_key": "",
        "label": "Google Gemini",
        "needs_api_key": "true",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-4-maverick:free",
        "api_key": "",
        "label": "OpenRouter",
        "needs_api_key": "true",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "model": "qwen3-32b",
        "api_key": "",
        "label": "Cerebras",
        "needs_api_key": "true",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "api_key": "",
        "label": "SambaNova",
        "needs_api_key": "true",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "api_key": "",
        "label": "Mistral",
        "needs_api_key": "true",
    },
    # ── Paid / trial API providers ──
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
        "label": "DeepSeek",
        "needs_api_key": "true",
    },
    "anthropic-api": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-6",
        "api_key": "",
        "label": "Anthropic",
        "needs_api_key": "true",
    },
    "openai-api": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "api_key": "",
        "label": "OpenAI",
        "needs_api_key": "true",
    },
    # ── Local models ──
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2:3b",
        "api_key": "ollama",
        "label": "Ollama",
    },
    # ── Internal / proxy (hidden from public UI) ──
    "claude-proxy": {
        "base_url": "http://localhost:8317/v1",
        "model": "claude-sonnet-4-20250514",
        "api_key": "not-needed",
        "label": "Claude Proxy (CLIProxyAPI)",
        "internal": "true",
    },
    "claude-proxy-alt": {
        "base_url": "http://localhost:3456/v1",
        "model": "claude-sonnet-4",
        "api_key": "not-needed",
        "label": "Claude Proxy (claude-max-api-proxy)",
        "internal": "true",
    },
    "openai-proxy": {
        "base_url": "http://localhost:3457/v1",
        "model": "gpt-4o",
        "api_key": "not-needed",
        "label": "OpenAI Proxy (Codex)",
        "internal": "true",
    },
}


class LLMClient:
    """Thin wrapper around the ``openai`` Python package.

    By swapping *base_url* you can target any OpenAI-compatible endpoint:
    local subscription proxies, cloud APIs, or Ollama.
    """

    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        load_dotenv()

        self.provider = provider or os.getenv("LLM_PROVIDER", "")
        preset = PRESETS.get(self.provider, {})

        self.base_url = base_url or os.getenv("LLM_BASE_URL", "") or preset.get("base_url", "")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "") or _get_keychain_key() or preset.get("api_key", "")
        self.model = model or os.getenv("LLM_MODEL", "") or preset.get("model", "")

        self._client = None
        if self.base_url and self.model:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.api_key or "not-needed",
                    base_url=self.base_url,
                    timeout=180.0,
                )
            except ImportError:
                logger.warning("openai package not installed. LLM features disabled.")

    # -- public API -------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """Return True if a provider is set up (may still be offline)."""
        return self._client is not None and bool(self.model)


    def is_available(self) -> bool:
        """Verify the LLM can actually complete a request.

        Earlier versions just pinged /health or /models, which passes for
        proxies that are online but reject real inference calls (e.g.
        consumer-subscription proxies returning auth_unavailable). Now we
        send a 1-token completion. If the model returns anything, it works.
        """
        if not self.is_configured:
            return False
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                temperature=0,
            )
            return bool(response.choices)
        except Exception as exc:
            msg = str(exc).lower()
            # Auth / permission errors → definitively unavailable
            if any(term in msg for term in [
                "auth", "401", "403", "permission", "unauthorized",
                "invalid api key", "api key",
            ]):
                return False
            # Other transient errors (timeout, rate limit, 500) → try
            # a lighter /models check before giving up
            try:
                url = self.base_url.rstrip("/")
                headers: dict[str, str] = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                r = requests.get(f"{url}/models", headers=headers, timeout=5)
                return r.status_code < 400
            except Exception:
                return False

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: str | None = None,
        json_mode: bool = False,
    ) -> str | None:
        """Send a chat completion request and return the assistant text.

        Returns *None* on any failure so callers can gracefully degrade.
        """
        if not self.is_configured:
            return None
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
        except Exception as exc:
            # Fall back without json_mode if the provider rejects it
            if json_mode and ("response_format" in str(exc) or "json" in str(exc).lower()):
                logger.debug("Provider rejected response_format, retrying without it")
                kwargs.pop("response_format", None)
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                    return resp.choices[0].message.content
                except Exception as exc2:
                    logger.error("LLM call failed: %s", exc2)
                    return None
            logger.error("LLM call failed: %s", exc)
            return None

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> dict | None:
        """Like :meth:`chat` but parses the response as JSON.

        The *system_prompt* should instruct the model to reply with valid JSON.
        Uses ``response_format: json_object`` when the provider supports it.
        """
        raw = self.chat(
            system_prompt, user_message,
            temperature=temperature, max_tokens=max_tokens,
            model=model, json_mode=True,
        )
        if raw is None:
            return None
        parsed = _parse_loose_json(raw)
        if parsed is not None:
            return parsed
        logger.error("Failed to parse LLM JSON response: %s…", _strip_markdown_fences(raw)[:200])
        return None

    def get_provider_info(self) -> dict[str, str]:
        """Return human-readable config for the Settings UI."""
        preset = PRESETS.get(self.provider, {})
        return {
            "provider": self.provider or "none",
            "label": preset.get("label", self.provider or "Not configured"),
            "base_url": self.base_url,
            "model": self.model,
            "configured": str(self.is_configured),
        }
