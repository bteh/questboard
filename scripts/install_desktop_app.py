#!/usr/bin/env python3
"""Install the latest built Questboard.app into /Applications."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="frontend/src-tauri/target/x86_64-apple-darwin/release/bundle/macos/Questboard.app",
        help="Path to the built Questboard.app bundle.",
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
    source = (repo_root / args.source).resolve()
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
