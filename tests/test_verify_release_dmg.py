"""Release-gate checks for the public DMG.

Pins two real bugs from the 2026-09 signing work:
- Tauri notarizes and staples the .app but signs the DMG afterwards, so the
  DMG shipped with no ticket of its own. A downloaded copy was rejected as
  "Unnotarized Developer ID" even though the app inside was fine.
- ``spctl -t open`` on a disk image answers "Insufficient Context" unless it
  is given ``--context context:primary-signature``, so the first version of
  this gate failed a DMG that was actually notarized.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import verify_release_dmg


class TestGatekeeperVerdict:
    def test_dmg_check_passes_the_primary_signature_context(self, monkeypatch):
        seen: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "source=Notarized Developer ID", "")

        monkeypatch.setattr(verify_release_dmg.subprocess, "run", fake_run)
        verify_release_dmg._gatekeeper_verdict(
            Path("x.dmg"), "open", "--context", "context:primary-signature"
        )
        assert "--context" in seen[0]
        assert "context:primary-signature" in seen[0]


class TestNotarizationRequired:
    def test_unnotarized_verdict_is_rejected(self):
        with pytest.raises(SystemExit) as excinfo:
            verify_release_dmg._require_notarized(
                "rejected\nsource=Unnotarized Developer ID", "The DMG"
            )
        assert "not notarized" in str(excinfo.value)

    def test_notarized_verdict_passes(self):
        verify_release_dmg._require_notarized(
            "accepted\nsource=Notarized Developer ID", "The DMG"
        )

    def test_missing_ticket_names_the_tauri_ordering_cause(self, tmp_path, monkeypatch):
        dmg = tmp_path / "Questboard.dmg"
        dmg.write_bytes(b"not a real image")

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 65, "", "does not have a ticket stapled to it"
            )

        monkeypatch.setattr(verify_release_dmg.subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as excinfo:
            verify_release_dmg.verify(dmg)
        assert "no notarization ticket" in str(excinfo.value)
