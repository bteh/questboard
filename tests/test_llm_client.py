from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, SRC_PATH)

from job_finder.llm_client import LLMClient, _parse_loose_json


class _FakeCompletions:
    """Mimics a provider that rejects `temperature` (like claude-opus-4-8).

    Raises the real 400 message when a request includes ``temperature`` and
    succeeds once the caller drops it. Records every call so tests can assert
    the retry actually stripped the param.
    """

    def __init__(self, calls: list[dict]) -> None:
        self.calls = calls

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "temperature" in kwargs:
            raise Exception(
                "Error code: 400 - {'type': 'error', 'error': {'type': "
                "'invalid_request_error', 'message': '`temperature` is "
                "deprecated for this model.'}}"
            )
        message = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    def __init__(self, calls: list[dict]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(calls))


class TemperatureRejectionTest(unittest.TestCase):
    """Newer models (claude-opus-4-8) reject `temperature`; the client must
    strip it and retry rather than failing the whole call (which surfaced as
    resume analysis silently returning nothing)."""

    def _client(self, calls: list[dict]) -> LLMClient:
        client = LLMClient(base_url="http://localhost:9/v1", model="claude-opus-4-8")
        client._client = _FakeOpenAI(calls)
        return client

    def test_chat_retries_without_temperature(self) -> None:
        calls: list[dict] = []
        out = self._client(calls).chat("system", "user", temperature=0.3)
        self.assertEqual(out, '{"ok": true}')
        self.assertIn("temperature", calls[0])  # first attempt sent it
        self.assertNotIn("temperature", calls[1])  # retry dropped it

    def test_chat_json_succeeds_when_temperature_rejected(self) -> None:
        calls: list[dict] = []
        out = self._client(calls).chat_json("system", "return json")
        self.assertEqual(out, {"ok": True})

    def test_temperature_supported_model_makes_no_extra_call(self) -> None:
        """A model that accepts temperature must not trigger a needless retry."""
        calls: list[dict] = []

        class _OkCompletions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))]
                )

        client = LLMClient(base_url="http://localhost:9/v1", model="claude-sonnet-4-5")
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=_OkCompletions()))
        out = client.chat("system", "user", temperature=0.3)
        self.assertEqual(out, "hi")
        self.assertEqual(len(calls), 1)


class LooseJsonParsingTest(unittest.TestCase):
    def test_extracts_partial_string_arrays_from_truncated_json(self) -> None:
        raw = """{
  "roles": [
    "Director, Data Platform",
    "Lead Data Platform Engineer"
  ],
  "keywords": [
    "dbt",
    "lakehouse"
  ],
  "companies": [
    "Databricks",
    "Snowflake"
"""

        parsed = _parse_loose_json(raw)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["roles"], ["Director, Data Platform", "Lead Data Platform Engineer"])
        self.assertEqual(parsed["keywords"], ["dbt", "lakehouse"])
        self.assertEqual(parsed["companies"], ["Databricks", "Snowflake"])


if __name__ == "__main__":
    unittest.main()
