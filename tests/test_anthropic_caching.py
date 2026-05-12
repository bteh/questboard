"""Contract tests for the Anthropic native SDK path with prompt caching.

LLMClient routes AI scoring through Anthropic's ``messages.create`` with
``cache_control: ephemeral`` markers when the active provider is
Anthropic-backed. These tests pin:

1. ``_is_anthropic_provider`` detection across direct-API, cliproxyapi
   ports, and Claude-named models, and returns False for OpenAI/Gemini.
2. ``chat_json_anthropic_cached`` sends ``cache_control`` markers on the
   system prompt AND on the resume prefix block in the user message.
3. The combined ``[system + resume]`` prefix is split correctly at the
   ``</resume>`` boundary so the cache_control block aligns with a stable
   token boundary.
4. The native path falls back to ``chat_json`` when the anthropic SDK
   is missing OR when the SDK call raises.
5. The native path parses Anthropic's content-block response into the
   same JSON dict shape that ``chat_json`` returns.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _make_client(provider="claude-proxy", base_url="http://localhost:8317/v1",
                 model="claude-sonnet-4-5", api_key="test"):
    """Construct an LLMClient bypassing env vars."""
    LLMClient = importlib.import_module("job_finder.llm_client").LLMClient
    return LLMClient(provider=provider, base_url=base_url, model=model, api_key=api_key)


class ProviderDetectionTest(unittest.TestCase):
    def test_anthropic_api_provider_detected(self) -> None:
        c = _make_client(provider="anthropic-api", base_url="https://api.anthropic.com/v1",
                         model="claude-sonnet-4-5")
        self.assertTrue(c._is_anthropic_provider())

    def test_claude_proxy_provider_detected(self) -> None:
        c = _make_client(provider="claude-proxy", base_url="http://localhost:8317/v1",
                         model="claude-sonnet-4")
        self.assertTrue(c._is_anthropic_provider())

    def test_localhost_proxy_port_detected(self) -> None:
        c = _make_client(provider="custom", base_url="http://localhost:3456/v1",
                         model="something")
        self.assertTrue(c._is_anthropic_provider())

    def test_claude_model_name_detected(self) -> None:
        # Even with a custom provider name, a Claude model hints Anthropic.
        c = _make_client(provider="my-proxy", base_url="https://example.com/v1",
                         model="claude-haiku-4-5")
        self.assertTrue(c._is_anthropic_provider())

    def test_openai_provider_not_detected(self) -> None:
        c = _make_client(provider="openai", base_url="https://api.openai.com/v1",
                         model="gpt-4o")
        self.assertFalse(c._is_anthropic_provider())

    def test_gemini_provider_not_detected(self) -> None:
        c = _make_client(provider="gemini-api",
                         base_url="https://generativelanguage.googleapis.com/v1beta",
                         model="gemini-2.0-flash")
        self.assertFalse(c._is_anthropic_provider())


class AnthropicCachedCallTest(unittest.TestCase):
    """The native call shape: cache_control markers + content blocks."""

    def setUp(self) -> None:
        self.llm_mod = importlib.import_module("job_finder.llm_client")
        self.client = _make_client()

    def _fake_anthropic_response(self, text: str = '{"overall_score": 75}'):
        response = SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            usage=SimpleNamespace(
                input_tokens=100,
                cache_creation_input_tokens=2000,
                cache_read_input_tokens=0,
            ),
        )
        return response

    def test_cache_control_on_system_and_resume_prefix(self) -> None:
        """system block and the user-prefix block both get cache_control."""
        fake_create = MagicMock(return_value=self._fake_anthropic_response())
        fake_client = MagicMock(messages=MagicMock(create=fake_create))
        fake_anthropic_mod = MagicMock(Anthropic=MagicMock(return_value=fake_client))

        with patch.dict(sys.modules, {"anthropic": fake_anthropic_mod}):
            result = self.client.chat_json_anthropic_cached(
                "SYSTEM RUBRIC",
                "<resume>my resume body</resume><job>title here</job>",
                cache_prefix_in_user="my resume body",
            )

        self.assertEqual(result, {"overall_score": 75})
        kwargs = fake_create.call_args.kwargs

        # System: single block, marked cacheable.
        self.assertEqual(len(kwargs["system"]), 1)
        self.assertEqual(kwargs["system"][0]["type"], "text")
        self.assertEqual(kwargs["system"][0]["text"], "SYSTEM RUBRIC")
        self.assertEqual(kwargs["system"][0]["cache_control"], {"type": "ephemeral"})

        # User message: two content blocks, prefix cacheable, suffix not.
        user_msg = kwargs["messages"][0]
        self.assertEqual(user_msg["role"], "user")
        blocks = user_msg["content"]
        self.assertEqual(len(blocks), 2)
        # First block carries cache_control and ends at </resume>.
        self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})
        self.assertTrue(blocks[0]["text"].endswith("</resume>"))
        # Second block is the per-job remainder, NOT cached.
        self.assertNotIn("cache_control", blocks[1])
        self.assertIn("<job>", blocks[1]["text"])

    def test_no_cache_prefix_sends_single_block(self) -> None:
        """When cache_prefix_in_user is None, user message is a single uncached block."""
        fake_create = MagicMock(return_value=self._fake_anthropic_response())
        fake_client = MagicMock(messages=MagicMock(create=fake_create))
        fake_anthropic_mod = MagicMock(Anthropic=MagicMock(return_value=fake_client))

        with patch.dict(sys.modules, {"anthropic": fake_anthropic_mod}):
            self.client.chat_json_anthropic_cached("SYS", "USER MSG")

        blocks = fake_create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("cache_control", blocks[0])
        self.assertEqual(blocks[0]["text"], "USER MSG")

    def test_parses_anthropic_content_blocks_to_json(self) -> None:
        fake_create = MagicMock(return_value=self._fake_anthropic_response(
            '{"overall_score": 88, "recommendation": "STRONG_APPLY"}',
        ))
        fake_client = MagicMock(messages=MagicMock(create=fake_create))
        fake_anthropic_mod = MagicMock(Anthropic=MagicMock(return_value=fake_client))

        with patch.dict(sys.modules, {"anthropic": fake_anthropic_mod}):
            result = self.client.chat_json_anthropic_cached("SYS", "USR")

        self.assertEqual(result["overall_score"], 88)
        self.assertEqual(result["recommendation"], "STRONG_APPLY")

    def test_falls_back_to_chat_json_on_sdk_exception(self) -> None:
        """If messages.create raises, we degrade to the OpenAI-compatible path."""
        fake_create = MagicMock(side_effect=RuntimeError("network down"))
        fake_client = MagicMock(messages=MagicMock(create=fake_create))
        fake_anthropic_mod = MagicMock(Anthropic=MagicMock(return_value=fake_client))

        with patch.dict(sys.modules, {"anthropic": fake_anthropic_mod}), \
             patch.object(self.client, "chat_json", return_value={"fallback": True}) as fb:
            result = self.client.chat_json_anthropic_cached("SYS", "USR")

        self.assertEqual(result, {"fallback": True})
        fb.assert_called_once()

    def test_falls_back_when_anthropic_sdk_missing(self) -> None:
        """If `import anthropic` fails, fall through to chat_json transparently."""
        # Force ImportError by mapping anthropic → None in sys.modules with a
        # ModuleNotFoundError-raising loader.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("anthropic SDK missing")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import), \
             patch.object(self.client, "chat_json", return_value={"fallback": True}) as fb:
            result = self.client.chat_json_anthropic_cached("SYS", "USR")

        self.assertEqual(result, {"fallback": True})
        fb.assert_called_once()


if __name__ == "__main__":
    unittest.main()
