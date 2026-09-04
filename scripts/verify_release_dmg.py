"""Verify a release DMG the way a stranger's Mac sees it.

Gatekeeper only enforces on quarantined files, so a DMG checked in place
always looks fine. This copies the DMG, flags it as a browser download,
and asks Gatekeeper about the DMG and about the app inside it.
"""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

QUARANTINE_ATTR = "com.apple.quarantine"
SAFARI_DOWNLOAD_FLAG = "0083;00000000;Safari;"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a signed, notarized Questboard DMG")
    parser.add_argument("dmg", help="Path to the built DMG")
    return parser.parse_args()


def _gatekeeper_verdict(target: Path, kind: str, *extra: str) -> str:
    result = subprocess.run(
        ["spctl", "-a", "-vv", "-t", kind, *extra, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def _require_notarized(verdict: str, label: str) -> None:
    if "source=Notarized Developer ID" not in verdict:
        raise SystemExit(
            f"{label} is not notarized as a Developer ID build. Gatekeeper said:\n{verdict}"
        )


def _mount(dmg: Path, mountpoint: Path) -> None:
    result = subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", "-mountpoint",
         str(mountpoint), str(dmg)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "A downloaded copy of the DMG would not mount:\n"
            + result.stderr.decode("utf-8", "replace")[-2000:]
        )
    plistlib.loads(result.stdout)


def _detach(mountpoint: Path) -> None:
    subprocess.run(["hdiutil", "detach", "-quiet", str(mountpoint)], check=False)


def verify(dmg: Path) -> None:
    if not dmg.exists():
        raise SystemExit(f"DMG not found: {dmg}")

    stapled = subprocess.run(
        ["xcrun", "stapler", "validate", str(dmg)],
        capture_output=True,
        text=True,
        check=False,
    )
    if stapled.returncode != 0:
        raise SystemExit(
            "The DMG carries no notarization ticket. Tauri signs the DMG after it "
            "notarizes the app, so the DMG needs its own submit + staple pass.\n"
            + (stapled.stdout + stapled.stderr).strip()[-1000:]
        )

    with tempfile.TemporaryDirectory(prefix="questboard-download-") as temp:
        root = Path(temp)
        downloaded = root / dmg.name
        shutil.copy2(dmg, downloaded)
        subprocess.run(
            ["xattr", "-w", QUARANTINE_ATTR, SAFARI_DOWNLOAD_FLAG, str(downloaded)],
            check=True,
        )

        # A disk image has no context of its own; without this spctl answers
        # "Insufficient Context" instead of judging the signature.
        dmg_verdict = _gatekeeper_verdict(
            downloaded, "open", "--context", "context:primary-signature"
        )
        _require_notarized(dmg_verdict, "The DMG")

        mountpoint = root / "mnt"
        mountpoint.mkdir()
        _mount(downloaded, mountpoint)
        try:
            apps = list(mountpoint.glob("*.app"))
            if len(apps) != 1:
                raise SystemExit(
                    f"Expected exactly one .app in the DMG, found {len(apps)}"
                )
            app_verdict = _gatekeeper_verdict(apps[0], "install")
            _require_notarized(app_verdict, f"The app ({apps[0].name})")
        finally:
            _detach(mountpoint)

    size_mb = dmg.stat().st_size / 1_000_000
    print(f"Release DMG verified as a fresh download: {dmg.name} ({size_mb:.0f} MB)")
    print("  Gatekeeper opens it with no warning on a Mac that has never seen it.")


def main() -> None:
    verify(Path(parse_args().dmg).resolve())


if __name__ == "__main__":
    main()
