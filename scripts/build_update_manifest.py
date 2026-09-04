"""Write the latest.json that installed copies poll for updates.

Tauri's updater fetches this file, compares its version against the running
app, and downloads the named archive only if the minisign signature matches
the public key baked into the app. A manifest whose URL or signature is
wrong fails closed: the app keeps running the version it has.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

# Tauri asks for the target it was built for, so the key must match exactly.
DARWIN_ARM64 = "darwin-aarch64"


def minisign_key_id(wrapped: str) -> str:
    """The 8-byte key id shared by a minisign public key and its signatures.

    Tauri base64-wraps the whole key/signature file, so unwrap once, drop the
    comment lines, then read the id out of the binary body.
    """
    text = base64.b64decode(wrapped).decode("utf-8")
    body = next(
        line
        for line in text.splitlines()
        if line and not line.startswith(("untrusted comment:", "trusted comment:"))
    )
    return base64.b64decode(body)[2:10].hex()


def assert_signed_by_shipped_key(signature: str, conf_path: Path) -> None:
    """Refuse a manifest the installed app could never verify.

    The app only trusts plugins.updater.pubkey. If the build signed with a
    different key, every update fails silently on the user's machine months
    later, so it has to fail here instead.
    """
    conf = json.loads(conf_path.read_text())
    pubkey = conf.get("plugins", {}).get("updater", {}).get("pubkey", "")
    if not pubkey:
        raise SystemExit(f"No plugins.updater.pubkey in {conf_path}")
    try:
        expected = minisign_key_id(pubkey)
        actual = minisign_key_id(signature)
    except (ValueError, StopIteration, UnicodeDecodeError) as exc:
        raise SystemExit(f"Could not read the updater key ids: {exc}") from exc
    if expected != actual:
        raise SystemExit(
            "The update was signed with a different key than the app trusts.\n"
            f"  app trusts: {expected}\n"
            f"  signed by:  {actual}\n"
            "Installed copies would reject this update. Check "
            "TAURI_SIGNING_PRIVATE_KEY against plugins.updater.pubkey."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Questboard update manifest")
    parser.add_argument("--bundle-dir", required=True, help="Directory holding the .app.tar.gz")
    parser.add_argument("--version", required=True, help="Version being released")
    parser.add_argument("--repo", default="bteh/questboard", help="GitHub owner/repo")
    parser.add_argument("--notes", default="", help="What changed, shown by some clients")
    parser.add_argument("--out", required=True, help="Where to write latest.json")
    parser.add_argument(
        "--tauri-conf",
        default="frontend/src-tauri/tauri.conf.json",
        help="Config holding the public key installed copies verify against",
    )
    return parser.parse_args()


def find_update_archive(bundle_dir: Path) -> tuple[Path, Path]:
    """Locate the update archive and its detached signature.

    Tauri only writes these when bundle.createUpdaterArtifacts is on, so a
    missing pair means the build silently shipped without update support.
    """
    archives = sorted(bundle_dir.glob("*.app.tar.gz"))
    if not archives:
        raise SystemExit(
            f"No .app.tar.gz in {bundle_dir}. Is bundle.createUpdaterArtifacts still true?"
        )
    if len(archives) > 1:
        raise SystemExit(
            "Multiple update archives found; a stale one would ship as the update: "
            + ", ".join(path.name for path in archives)
        )
    archive = archives[0]
    signature = archive.with_suffix(archive.suffix + ".sig")
    if not signature.exists():
        raise SystemExit(
            f"Update archive has no signature next to it: {signature.name}. "
            "The build needs TAURI_SIGNING_PRIVATE_KEY set."
        )
    return archive, signature


def build_manifest(archive: Path, signature: Path, version: str, repo: str, notes: str) -> dict:
    url = (
        f"https://github.com/{repo}/releases/download/"
        f"v{version}/{archive.name}"
    )
    return {
        "version": version,
        "notes": notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": {
            DARWIN_ARM64: {
                "signature": signature.read_text().strip(),
                "url": url,
            }
        },
    }


def main() -> None:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).resolve()
    archive, signature = find_update_archive(bundle_dir)
    manifest = build_manifest(archive, signature, args.version, args.repo, args.notes)
    assert_signed_by_shipped_key(
        manifest["platforms"][DARWIN_ARM64]["signature"],
        Path(args.tauri_conf).resolve(),
    )

    out = Path(args.out).resolve()
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Update manifest written: {out}")
    print(f"  version {manifest['version']} -> {manifest['platforms'][DARWIN_ARM64]['url']}")
    print(f"  upload both {archive.name} and {out.name} to the v{args.version} release")


if __name__ == "__main__":
    main()
