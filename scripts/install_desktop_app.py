#!/usr/bin/env python3
"""Install the latest built Questboard.app into /Applications."""

from __future__ import annotations

import argparse
import platform
import shutil
from datetime import datetime
from pathlib import Path

_BUNDLE_GLOB = "*/release/bundle/macos/Questboard.app"


def discover_app(repo_root: Path) -> Path | None:
    """Find the freshest built Questboard.app, preferring the host arch.

    The Tauri build target follows the venv Python's arch (aarch64 or
    x86_64), so the built bundle lives under the matching target triple.
    Prefer that, fall back to any, newest by mtime, so this keeps working
    whichever arch the last build produced.
    """
    base = repo_root / "frontend" / "src-tauri" / "target"
    triple = "aarch64-apple-darwin" if platform.machine() == "arm64" else "x86_64-apple-darwin"
    candidates = list(base.glob(f"{triple}/release/bundle/macos/Questboard.app"))
    if not candidates:
        candidates = list(base.glob(_BUNDLE_GLOB))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=None,
        help="Path to the built Questboard.app bundle. Auto-discovered by arch when omitted.",
    )
    parser.add_argument(
        "--destination",
        default="/Applications/Questboard.app",
        help="Install destination for the app bundle.",
    )
    parser.add_argument(
        "--backup-dir",
        default=".desktop-build/install-backups",
        help="Directory where replaced app bundles are backed up.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    if args.source:
        source = (repo_root / args.source).resolve()
    else:
        discovered = discover_app(repo_root)
        if discovered is None:
            raise SystemExit(
                "No built Questboard.app found under frontend/src-tauri/target. "
                "Run 'make desktop-build' first."
            )
        source = discovered.resolve()
    destination = Path(args.destination).resolve()
    backup_dir = (repo_root / args.backup_dir).resolve()

    if not source.exists():
        raise SystemExit(f"Built app not found at {source}. Run 'make desktop-build' first.")

    backup_dir.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_target = backup_dir / f"Questboard-{timestamp}.app"
        destination.rename(backup_target)
        print(f"Backed up existing app to {backup_target}")

    shutil.copytree(source, destination, dirs_exist_ok=False)
    print(f"Installed {source} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
