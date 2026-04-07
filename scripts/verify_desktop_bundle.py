"""Verify packaged desktop artifacts for structural correctness."""

from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Launchboard desktop bundle")
    parser.add_argument(
        "--bundle-root",
        default="frontend/src-tauri/target/release/bundle",
        help="Path to the Tauri bundle output root",
    )
    return parser.parse_args()


def _arch_set(path: Path) -> set[str]:
    result = subprocess.run(["file", str(path)], capture_output=True, text=True, check=True)
    output = result.stdout.lower()
    arches: set[str] = set()
    if "x86_64" in output:
        arches.add("x86_64")
    if "arm64" in output or "aarch64" in output:
        arches.add("arm64")
    return arches


def resolve_bundle_root(bundle_root: Path) -> Path:
    candidates: list[Path] = []
    if bundle_root.exists():
        candidates.append(bundle_root)

    target_root = bundle_root
    if bundle_root.name == "bundle" and bundle_root.parent.name == "release":
        target_root = bundle_root.parent.parent
    elif bundle_root.name == "release":
        target_root = bundle_root.parent

    if target_root.name == "target" and target_root.exists():
        candidates.extend(path for path in target_root.glob("*/release/bundle") if path.exists())

    if not candidates:
        raise SystemExit(f"Bundle output not found: {bundle_root}")

    return max(candidates, key=lambda path: path.stat().st_mtime)


def verify_macos_bundle(bundle_root: Path) -> None:
    app_binary = bundle_root / "macos" / "Launchboard.app" / "Contents" / "MacOS" / "launchboard-desktop"
    sidecar = bundle_root / "macos" / "Launchboard.app" / "Contents" / "Resources" / "sidecars" / "launchboard-runtime"
    dmg_dir = bundle_root / "dmg"

    if not app_binary.exists():
        raise SystemExit(f"Missing app binary: {app_binary}")
    if not sidecar.exists():
        raise SystemExit(f"Missing packaged sidecar: {sidecar}")
    if not dmg_dir.exists():
        raise SystemExit(f"Missing DMG output directory: {dmg_dir}")

    app_arches = _arch_set(app_binary)
    sidecar_arches = _arch_set(sidecar)
    if not app_arches:
        raise SystemExit(f"Unable to determine app binary architecture: {app_binary}")
    if not sidecar_arches:
        raise SystemExit(f"Unable to determine sidecar architecture: {sidecar}")
    if app_arches != sidecar_arches:
        raise SystemExit(
            "App binary and packaged sidecar architectures do not match: "
            f"app={sorted(app_arches)} sidecar={sorted(sidecar_arches)}"
        )


def main() -> None:
    args = parse_args()
    bundle_root = resolve_bundle_root(Path(args.bundle_root).resolve())
    system = platform.system()

    if system == "Darwin":
        verify_macos_bundle(bundle_root)
    else:
        raise SystemExit(f"Bundle verification is not implemented for {system} yet")

    print(f"Desktop bundle verified: {bundle_root}")


if __name__ == "__main__":
    main()
