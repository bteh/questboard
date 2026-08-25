"""Clean up leftover rw.*.dmg temp images before a desktop build.

A failed or interrupted `tauri build` leaves the rw.<pid>.<name>.dmg
working image hdiutil was writing (~175MB each, they pile up fast), and
one that is still mounted makes every later DMG build die with
"resource busy". This detaches only volumes whose backing image lives
inside THIS repo's Tauri target dir, then deletes the stale files.
Volumes and images anywhere else are never touched.
"""

from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from pathlib import Path

RW_IMAGE_NAME = re.compile(r"^rw\..+\.dmg$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tauri_target_dir() -> Path:
    return repo_root() / "frontend" / "src-tauri" / "target"


def rw_disks_to_detach(hdiutil_plist: bytes, target_dir: Path) -> list[str]:
    """One whole-disk /dev entry per mounted rw.*.dmg inside target_dir."""
    try:
        info = plistlib.loads(hdiutil_plist)
    except Exception:
        return []
    resolved_target = target_dir.resolve()
    disks: list[str] = []
    for image in info.get("images", []):
        image_path = str(image.get("image-path", "") or "")
        if not image_path or not RW_IMAGE_NAME.match(Path(image_path).name):
            continue
        try:
            if not Path(image_path).resolve().is_relative_to(resolved_target):
                continue
        except (OSError, ValueError):
            continue
        entries = [
            str(entity.get("dev-entry", "") or "")
            for entity in image.get("system-entities", [])
        ]
        entries = [entry for entry in entries if entry]
        if entries:
            # the shortest entry is the whole disk; detaching it takes
            # every slice with it
            disks.append(min(entries, key=len))
    return disks


def stale_rw_images(target_dir: Path) -> list[Path]:
    if not target_dir.exists():
        return []
    found: set[Path] = set()
    for pattern in ("*/release/bundle/**/rw.*.dmg", "release/bundle/**/rw.*.dmg"):
        for path in target_dir.glob(pattern):
            if path.is_file() and RW_IMAGE_NAME.match(path.name):
                found.add(path)
    return sorted(found)


def detach_zombie_mounts(target_dir: Path) -> int:
    if sys.platform != "darwin":
        return 0
    result = subprocess.run(
        ["hdiutil", "info", "-plist"], capture_output=True, check=False
    )
    if result.returncode != 0:
        return 0
    detached = 0
    for disk in rw_disks_to_detach(result.stdout, target_dir):
        outcome = subprocess.run(
            ["hdiutil", "detach", disk], capture_output=True, check=False
        )
        if outcome.returncode != 0:
            outcome = subprocess.run(
                ["hdiutil", "detach", disk, "-force"], capture_output=True, check=False
            )
        if outcome.returncode == 0:
            print(f"Detached zombie DMG volume {disk}")
            detached += 1
        else:
            print(f"WARNING: could not detach {disk}: {outcome.stderr.decode().strip()}")
    return detached


def delete_stale_images(target_dir: Path) -> int:
    freed = 0
    count = 0
    for path in stale_rw_images(target_dir):
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            print(f"WARNING: could not delete {path}: {exc}")
            continue
        freed += size
        count += 1
    if count:
        print(f"Deleted {count} stale rw.*.dmg image(s), freed {freed / 1e9:.1f} GB")
    return count


def main() -> None:
    target_dir = tauri_target_dir()
    detach_zombie_mounts(target_dir)
    delete_stale_images(target_dir)


if __name__ == "__main__":
    main()
