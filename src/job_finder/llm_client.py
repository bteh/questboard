"""Unified LLM client that works with any OpenAI-compatible endpoint.

Supports subscription proxies (CLIProxyAPI, claude-max-api-proxy),
direct APIs (Anthropic, OpenAI, Gemini), and local models (Ollama).
"""

from __future__ import annotations

import json
import logging
import os

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Provider presets -------------------------------------------------------

PRESETS: dict[str, dict[str, str]] = {
    "claude-proxy": {
        "base_url": "http://localhost:8317/v1",
        "model": "claude-sonnet-4-20250514",
        "api_key": "not-needed",
        "label": "Claude Proxy (CLIProxyAPI)",
    },
    "claude-proxy-alt": {
        "base_url": "http://localhost:3456/v1",
        "model": "claude-sonnet-4",
        "api_key": "not-needed",
        "label": "Claude Proxy (claude-max-api-proxy)",
    },
    "openai-proxy": {
        "base_url": "http://localhost:3457/v1",
        "model": "gpt-4o",
        "api_key": "not-needed",
        "label": "OpenAI Proxy (Codex)",
    },
    "anthropic-api": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
        "api_key": "",
        "label": "Anthropic API (pay-per-use)",
    },
    "openai-api": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "api_key": "",
        "label": "OpenAI API (pay-per-use)",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "api_key": "",
        "label": "Google Gemini (free tier available)",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "api_key": "ollama",
        "label": "Ollama (local)",
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
        self.api_key = api_key or os.getenv("LLM_API_KEY", "") or preset.get("api_key", "")
        self.model = model or os.getenv("LLM_MODEL", "") or preset.get("model", "")

        self._client = None
        if self.base_url and self.model:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.api_key or "not-needed",
                    base_url=self.base_url,
                    timeout=120.0,
                )
            except ImportError:
                logger.warning("openai package not installed. LLM features disabled.")

    # -- public API -------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """Return True if a provider is set up (may still be offline)."""
        return self._client is not None and bool(self.model)

    def is_available(self) -> bool:
        """Health-check: try to reach the endpoint."""
        if not self.is_configured:
            return False
        try:
            url = self.base_url.rstrip("/")
            # Try /models first (standard OpenAI), fall back to /health
            for path in ["/models", "/../health"]:
                try:
                    r = requests.get(f"{url}{path}", timeout=5)
                    if r.status_code < 500:
                        return True
                except requests.ConnectionError:
                    continue
            return False
        except Exception:
            return False

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Send a chat completion request and return the assistant text.

        Returns *None* on any failure so callers can gracefully degrade.
        """
        if not self.is_configured:
            return None
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return None

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict | None:
        """Like :meth:`chat` but parses the response as JSON.

        The *system_prompt* should instruct the model to reply with valid JSON.
        """
        raw = self.chat(system_prompt, user_message, temperature=temperature, max_tokens=max_tokens)
        if raw is None:
            return None
        # Strip markdown code fences if the model wraps its answer
        text = raw.strip()
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = text.index("\n") if "\n" in text else 3
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM JSON response: %s…", text[:200])
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
