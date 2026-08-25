"""The desktop shell must never attach its window to a stranger's backend.

/health echoes QUESTBOARD_LAUNCH_NONCE when the sidecar was spawned with
one, so the Tauri shell can prove the healthy answer came from its own
child and not another Questboard (or anything else) holding the port.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

from app.api.health import health


def test_health_echoes_the_launch_nonce_from_its_own_env(monkeypatch):
    monkeypatch.setenv("QUESTBOARD_LAUNCH_NONCE", "abc123")
    assert health() == {"status": "ok", "launch_nonce": "abc123"}


def test_health_without_a_nonce_stays_plain(monkeypatch):
    monkeypatch.delenv("QUESTBOARD_LAUNCH_NONCE", raising=False)
    assert health() == {"status": "ok"}
