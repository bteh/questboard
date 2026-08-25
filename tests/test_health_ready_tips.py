"""/health/ready tips must speak the surface's language.

The packaged desktop app has no 'make setup', no .env, and no knowledge/
directory a user can see, so its tips point at Settings instead of the
dev workflow. Web/dev mode keeps the original contributor-facing tips.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from app.api.health import _get_tips


class TestDevTips:
    def test_fresh_checkout_keeps_contributor_tips(self):
        tips = _get_tips("", False, False, [], desktop=False)
        assert "Run 'questboard-setup' or 'make setup' to create your first profile" in tips
        assert "Set LLM_PROVIDER in .env for AI scoring (search works without it)" in tips

    def test_configured_llm_unreachable(self):
        tips = _get_tips("ollama", False, True, ["default"], desktop=False)
        assert tips == ["LLM provider 'ollama' is configured but not reachable"]


class TestDesktopTips:
    def test_fresh_install_gets_plain_settings_copy(self):
        tips = _get_tips("", False, False, [], desktop=True)
        assert "Add your resume and roles in Settings" in tips
        assert "Connect an assistant in Settings, Assistant tab. Optional." in tips

    def test_no_dev_jargon_in_any_desktop_tip(self):
        for llm_provider, llm_available, resume_found, profiles in [
            ("", False, False, []),
            ("", False, True, ["default"]),
            ("ollama", False, False, []),
            ("ollama", True, True, ["default"]),
        ]:
            tips = _get_tips(
                llm_provider, llm_available, resume_found, profiles, desktop=True
            )
            joined = " ".join(tips)
            for jargon in ("make setup", "questboard-setup", ".env", "LLM_PROVIDER", "knowledge/"):
                assert jargon not in joined, f"{jargon!r} leaked into desktop tips: {tips}"

    def test_desktop_unreachable_assistant_points_at_settings(self):
        tips = _get_tips("ollama", False, True, ["default"], desktop=True)
        assert tips == [
            "Your assistant (ollama) is set up but not answering. Check Settings, Assistant tab."
        ]

    def test_fully_configured_desktop_has_no_tips(self):
        assert _get_tips("ollama", True, True, ["default"], desktop=True) == []
