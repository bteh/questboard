"""The update manifest is the one file that can break every installed copy.

A wrong URL or a missing signature does not fail loudly at build time; it
fails months later on a stranger's machine that quietly stops updating. So
each way of getting it wrong is pinned here.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import build_update_manifest


def _archive(bundle: Path, name: str = "Questboard_0.2.0_aarch64.app.tar.gz") -> Path:
    archive = bundle / name
    archive.write_bytes(b"tarball")
    return archive


class TestFindUpdateArchive:
    def test_missing_archive_names_the_config_switch(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            build_update_manifest.find_update_archive(tmp_path)
        assert "createUpdaterArtifacts" in str(excinfo.value)

    def test_unsigned_archive_is_refused(self, tmp_path):
        _archive(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            build_update_manifest.find_update_archive(tmp_path)
        assert "TAURI_SIGNING_PRIVATE_KEY" in str(excinfo.value)

    def test_stale_second_archive_is_refused(self, tmp_path):
        for name in ("Questboard_0.1.0_aarch64.app.tar.gz", "Questboard_0.2.0_aarch64.app.tar.gz"):
            archive = _archive(tmp_path, name)
            archive.with_suffix(archive.suffix + ".sig").write_text("sig")
        with pytest.raises(SystemExit) as excinfo:
            build_update_manifest.find_update_archive(tmp_path)
        assert "Multiple update archives" in str(excinfo.value)

    def test_signed_archive_is_found(self, tmp_path):
        archive = _archive(tmp_path)
        archive.with_suffix(archive.suffix + ".sig").write_text("sig")
        found, signature = build_update_manifest.find_update_archive(tmp_path)
        assert found.name == archive.name
        assert signature.read_text() == "sig"


class TestSignedByShippedKey:
    """The manifest must be signed by the key the installed app trusts.

    A mismatch is invisible at build time and silently stops every installed
    copy from updating, so it is checked before the manifest is written.
    """

    @staticmethod
    def _wrapped(key_id: bytes, comment: str) -> str:
        body = base64.b64encode(b"Ed" + key_id + b"\x00" * 32).decode()
        return base64.b64encode(f"untrusted comment: {comment}\n{body}\n".encode()).decode()

    def _conf(self, tmp_path: Path, pubkey: str) -> Path:
        conf = tmp_path / "tauri.conf.json"
        conf.write_text(json.dumps({"plugins": {"updater": {"pubkey": pubkey}}}))
        return conf

    def test_matching_key_passes(self, tmp_path):
        key_id = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        conf = self._conf(tmp_path, self._wrapped(key_id, "minisign public key"))
        build_update_manifest.assert_signed_by_shipped_key(
            self._wrapped(key_id, "signature from tauri secret key"), conf
        )

    def test_wrong_key_is_refused_with_both_ids(self, tmp_path):
        conf = self._conf(tmp_path, self._wrapped(b"\x01" * 8, "minisign public key"))
        with pytest.raises(SystemExit) as excinfo:
            build_update_manifest.assert_signed_by_shipped_key(
                self._wrapped(b"\x02" * 8, "signature from tauri secret key"), conf
            )
        message = str(excinfo.value)
        assert "different key" in message
        assert "0101010101010101" in message
        assert "0202020202020202" in message

    def test_config_without_a_pubkey_is_refused(self, tmp_path):
        conf = tmp_path / "tauri.conf.json"
        conf.write_text(json.dumps({"plugins": {}}))
        with pytest.raises(SystemExit) as excinfo:
            build_update_manifest.assert_signed_by_shipped_key("x", conf)
        assert "pubkey" in str(excinfo.value)


class TestManifestShape:
    def test_url_points_at_the_tagged_release_asset(self, tmp_path):
        archive = _archive(tmp_path)
        signature = archive.with_suffix(archive.suffix + ".sig")
        signature.write_text("  signature-body  \n")

        manifest = build_update_manifest.build_manifest(
            archive, signature, "0.2.0", "bteh/questboard", ""
        )
        platform = manifest["platforms"][build_update_manifest.DARWIN_ARM64]
        assert platform["url"] == (
            "https://github.com/bteh/questboard/releases/download/"
            "v0.2.0/Questboard_0.2.0_aarch64.app.tar.gz"
        )
        # A signature with stray whitespace fails verification on the client.
        assert platform["signature"] == "signature-body"

    def test_manifest_is_valid_json_with_the_version_tauri_compares(self, tmp_path):
        archive = _archive(tmp_path)
        archive.with_suffix(archive.suffix + ".sig").write_text("sig")
        manifest = build_update_manifest.build_manifest(
            archive, archive.with_suffix(archive.suffix + ".sig"),
            "0.2.0", "bteh/questboard", "notes",
        )
        round_tripped = json.loads(json.dumps(manifest))
        assert round_tripped["version"] == "0.2.0"
        assert round_tripped["notes"] == "notes"
        assert round_tripped["pub_date"].endswith("Z")
