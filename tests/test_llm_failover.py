"""Failover across free LLM lanes: primary -> fallback -> keyword floor.

Covers FailoverLLMClient's circuit breaker and build_llm's lane assembly.
Uses fake lanes so nothing hits the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import job_finder.llm_client as mod  # noqa: E402
from job_finder.llm_client import (  # noqa: E402
    FailoverLLMClient,
    LLMClient,
    build_llm,
)


class FakeLane:
    """Mimics the LLMClient surface FailoverLLMClient reads."""

    def __init__(self, provider="fake", *, configured=True, available=True,
                 responses=None, always=None):
        self.provider = provider
        self.model = f"{provider}-model"
        self.base_url = f"https://{provider}.test/v1"
        self.api_key = "k"
        self.last_error = None
        self.is_configured = configured
        self._available = available
        # `responses` is a scripted list (then None forever); `always` is one value.
        self._responses = list(responses) if responses is not None else None
        self._always = always
        self.calls = 0

    def is_available(self, force=False):
        return self._available

    def _next(self):
        self.calls += 1
        if self._responses is not None:
            return self._responses.pop(0) if self._responses else None
        return self._always

    def chat_json(self, *a, **k):
        return self._next()

    def chat(self, *a, **k):
        return self._next()

    def chat_json_anthropic_cached(self, *a, **k):
        return self._next()

    def _is_anthropic_provider(self):
        return False

    def get_provider_info(self):
        return {"provider": self.provider, "model": self.model}


def test_first_healthy_lane_wins():
    a = FakeLane("groq", always={"a": 1})
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    assert fc.chat_json("s", "u") == {"a": 1}
    assert a.calls == 1
    assert b.calls == 0  # fallback never touched when primary answers


def test_falls_through_to_second_lane_on_failure():
    a = FakeLane("groq", always=None)
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    assert fc.chat_json("s", "u") == {"b": 2}
    assert a.calls == 1 and b.calls == 1


def test_lane_benched_after_threshold_then_skipped():
    a = FakeLane("groq", always=None)
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    for _ in range(3):
        assert fc.chat_json("s", "u") == {"b": 2}
    assert a.calls == 3  # tried on the first three, then benched
    assert fc.chat_json("s", "u") == {"b": 2}
    assert a.calls == 3  # skipped on the fourth
    assert b.calls == 4


def test_all_lanes_down_returns_none_and_stops_hammering():
    a = FakeLane("groq", always=None)
    b = FakeLane("cerebras", always=None)
    fc = FailoverLLMClient([a, b])
    for _ in range(3):
        assert fc.chat_json("s", "u") is None  # -> caller's keyword floor
    assert a.calls == 3 and b.calls == 3
    # both benched: returns None without calling either again
    assert fc.chat_json("s", "u") is None
    assert a.calls == 3 and b.calls == 3


def test_success_resets_failure_streak():
    # A never fails 3 in a row, so it is never benched.
    a = FakeLane("groq", responses=[None, None, {"a": 1}, None, None])
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    results = [fc.chat_json("s", "u") for _ in range(5)]
    assert results == [{"b": 2}, {"b": 2}, {"a": 1}, {"b": 2}, {"b": 2}]
    assert a.calls == 5


def test_is_available_true_if_any_lane_available():
    assert FailoverLLMClient(
        [FakeLane("groq", available=False), FakeLane("cerebras", available=True)]
    ).is_available() is True
    assert FailoverLLMClient(
        [FakeLane("groq", available=False), FakeLane("cerebras", available=False)]
    ).is_available() is False


def test_reported_attributes_follow_the_active_lane():
    a = FakeLane("groq", always=None)
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    assert fc.provider == "groq"  # A is live first
    for _ in range(3):
        fc.chat_json("s", "u")  # bench A
    assert fc.provider == "cerebras"


def test_benched_lane_recovers_after_cooldown(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(mod.time, "time", lambda: fake_now[0])
    a = FakeLane("groq", always=None)
    b = FakeLane("cerebras", always={"b": 2})
    fc = FailoverLLMClient([a, b])
    for _ in range(3):
        fc.chat_json("s", "u")  # bench A at t=1000
    assert a.calls == 3
    fc.chat_json("s", "u")  # still benched
    assert a.calls == 3
    fake_now[0] = 1000.0 + FailoverLLMClient._COOLDOWN + 1
    fc.chat_json("s", "u")  # cooldown elapsed -> A tried again
    assert a.calls == 4


# -- build_llm lane assembly -------------------------------------------------

_LANE_ENVS = (
    "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY",
    "GROQ_API_KEY", "CEREBRAS_API_KEY",
)


def _clear_lane_env(monkeypatch):
    # Set to "" rather than delete: LLMClient.__init__ calls load_dotenv(), which
    # would otherwise refill these from the repo .env (which now holds a real
    # provider). load_dotenv(override=False) leaves a present-but-empty var alone.
    for k in _LANE_ENVS:
        monkeypatch.setenv(k, "")


def test_build_llm_single_lane_is_unwrapped(monkeypatch):
    _clear_lane_env(monkeypatch)
    llm = build_llm(provider="groq", api_key="fake")
    assert isinstance(llm, LLMClient)
    assert not isinstance(llm, FailoverLLMClient)
    assert llm.is_configured


def test_build_llm_wraps_when_a_fallback_key_is_present(monkeypatch):
    _clear_lane_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_API_KEY", "fake-cerebras")
    llm = build_llm(provider="groq", api_key="fake-groq")
    assert isinstance(llm, FailoverLLMClient)
    assert llm.is_configured
    assert llm.provider == "groq"  # primary stays first in the chain


def test_build_llm_unconfigured_when_no_keys(monkeypatch):
    _clear_lane_env(monkeypatch)
    llm = build_llm()
    assert not llm.is_configured
