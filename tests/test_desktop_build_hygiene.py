"""Desktop build hygiene: stale sidecars and leftover rw.*.dmg images.

Pins two real shipping bugs from the 2026-08 build audit:
- The DMG shipped a stale ``launchboard-runtime`` because tauri.conf.json
  bundles the whole ``tauri-sidecars/*`` glob and the sidecar build only
  ever unlinked its own target name.
- Failed hdiutil runs left ~28 rw.*.dmg temp images (7.7GB) in the bundle
  output dir, and a mounted zombie image broke every later DMG build.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import build_desktop_sidecar
import clean_dmg_artifacts
import verify_desktop_bundle


class TestStagingDirReset:
    def test_reset_removes_stale_entries(self, tmp_path):
        staging = tmp_path / "tauri-sidecars"
        staging.mkdir()
        (staging / "launchboard-runtime").write_bytes(b"stale binary")
        (staging / "notes").mkdir()

        build_desktop_sidecar.reset_staging_dir(staging)

        assert staging.exists()
        assert list(staging.iterdir()) == []

    def test_reset_creates_missing_dir(self, tmp_path):
        staging = tmp_path / "nested" / "tauri-sidecars"
        build_desktop_sidecar.reset_staging_dir(staging)
        assert staging.is_dir()

    def test_build_sidecar_starts_from_clean_staging(self, tmp_path, monkeypatch):
        staging = tmp_path / "tauri-sidecars"
        staging.mkdir()
        (staging / "launchboard-runtime").write_bytes(b"stale binary")
        monkeypatch.setattr(build_desktop_sidecar, "sidecar_dir", lambda: staging)
        monkeypatch.setattr(
            build_desktop_sidecar, "pyinstaller_work_dir", lambda: tmp_path / "work"
        )

        def fake_run(command, **kwargs):
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, stdout="6.0\n", stderr="")
            (staging / build_desktop_sidecar.sidecar_name()).write_bytes(b"built")
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(build_desktop_sidecar.subprocess, "run", fake_run)

        built = build_desktop_sidecar.build_sidecar()

        assert built.name == build_desktop_sidecar.sidecar_name()
        assert sorted(p.name for p in staging.iterdir()) == [
            build_desktop_sidecar.sidecar_name()
        ]


class TestBundleSidecarPin:
    def test_flags_files_not_named_questboard_runtime(self, tmp_path):
        sidecars = tmp_path / "sidecars"
        sidecars.mkdir()
        (sidecars / "questboard-runtime").write_bytes(b"ok")
        (sidecars / "launchboard-runtime").write_bytes(b"stale")

        strays = verify_desktop_bundle.unexpected_sidecar_files(sidecars)

        assert [p.name for p in strays] == ["launchboard-runtime"]

    def test_accepts_only_expected_sidecar(self, tmp_path):
        sidecars = tmp_path / "sidecars"
        sidecars.mkdir()
        (sidecars / "questboard-runtime").write_bytes(b"ok")
        assert verify_desktop_bundle.unexpected_sidecar_files(sidecars) == []

    def test_missing_dir_is_empty(self, tmp_path):
        assert verify_desktop_bundle.unexpected_sidecar_files(tmp_path / "nope") == []

    def test_verify_macos_bundle_fails_on_stray_sidecar(self, tmp_path):
        bundle_root = tmp_path / "bundle"
        app = bundle_root / "macos" / "Questboard.app" / "Contents"
        (app / "MacOS").mkdir(parents=True)
        (app / "MacOS" / "questboard-desktop").write_bytes(b"bin")
        sidecars = app / "Resources" / "sidecars"
        sidecars.mkdir(parents=True)
        (sidecars / "questboard-runtime").write_bytes(b"bin")
        (sidecars / "launchboard-runtime").write_bytes(b"stale")
        (bundle_root / "dmg").mkdir()

        with pytest.raises(SystemExit, match="launchboard-runtime"):
            verify_desktop_bundle.verify_macos_bundle(bundle_root)


def _plist(images: list[dict]) -> bytes:
    return plistlib.dumps({"images": images})


class TestDmgArtifactCleanup:
    def test_detach_only_rw_images_inside_target_dir(self, tmp_path):
        target = tmp_path / "frontend" / "src-tauri" / "target"
        target.mkdir(parents=True)
        inside = target / "aarch64-apple-darwin" / "release" / "bundle" / "macos"
        data = _plist(
            [
                {
                    "image-path": str(inside / "rw.84919.Questboard_0.2.0_aarch64.dmg"),
                    "system-entities": [
                        {"dev-entry": "/dev/disk4"},
                        {"dev-entry": "/dev/disk4s1", "mount-point": "/Volumes/Questboard"},
                    ],
                },
                {
                    "image-path": "/Users/someone/Downloads/rw.99.Other_1.0.dmg",
                    "system-entities": [{"dev-entry": "/dev/disk5"}],
                },
                {
                    "image-path": str(inside / "Questboard_0.2.0_aarch64.dmg"),
                    "system-entities": [{"dev-entry": "/dev/disk6"}],
                },
            ]
        )

        assert clean_dmg_artifacts.rw_disks_to_detach(data, target) == ["/dev/disk4"]

    def test_detach_handles_empty_info(self, tmp_path):
        assert clean_dmg_artifacts.rw_disks_to_detach(_plist([]), tmp_path) == []

    def test_stale_rw_images_found_in_bundle_dirs_only(self, tmp_path):
        target = tmp_path / "target"
        arch_bundle = target / "aarch64-apple-darwin" / "release" / "bundle" / "macos"
        arch_bundle.mkdir(parents=True)
        plain_bundle = target / "release" / "bundle" / "macos"
        plain_bundle.mkdir(parents=True)
        stale_a = arch_bundle / "rw.123.Questboard_0.2.0_aarch64.dmg"
        stale_a.write_bytes(b"x")
        stale_b = plain_bundle / "rw.9.Questboard_0.2.0.dmg"
        stale_b.write_bytes(b"x")
        keep_dmg = arch_bundle / "Questboard_0.2.0_aarch64.dmg"
        keep_dmg.write_bytes(b"x")
        elsewhere = target / "aarch64-apple-darwin" / "release" / "rw.5.stray.dmg"
        elsewhere.write_bytes(b"x")

        found = clean_dmg_artifacts.stale_rw_images(target)

        assert set(found) == {stale_a, stale_b}

    def test_stale_rw_images_missing_target(self, tmp_path):
        assert clean_dmg_artifacts.stale_rw_images(tmp_path / "absent") == []
