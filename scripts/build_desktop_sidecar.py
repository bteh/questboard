"""Build the packaged desktop runtime sidecar for the current OS."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sidecar_dir() -> Path:
    return repo_root() / ".desktop-build" / "tauri-sidecars"


def pyinstaller_work_dir() -> Path:
    return repo_root() / ".desktop-build" / "pyinstaller"


def sidecar_name() -> str:
    return "launchboard-runtime.exe" if sys.platform == "win32" else "launchboard-runtime"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Launchboard desktop sidecar")
    parser.add_argument(
        "--target-arch",
        default="",
        help="macOS target architecture for PyInstaller (x86_64, arm64, universal2)",
    )
    return parser.parse_args()


def build_sidecar(*, target_arch: str = "") -> Path:
    root = repo_root()
    output_dir = sidecar_dir()
    work_dir = pyinstaller_work_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    pyinstaller_module = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    if pyinstaller_module.returncode != 0:
        raise SystemExit(
            "PyInstaller is required for desktop builds. Install it with `./.venv/bin/python -m pip install pyinstaller`."
        )

    target_path = output_dir / sidecar_name()
    if target_path.exists():
        target_path.unlink()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "launchboard-runtime",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(work_dir / "build"),
        "--specpath",
        str(work_dir / "spec"),
        "--paths",
        str(root / "backend"),
        "--paths",
        str(root / "src"),
        # Bundle the keyring library + OS backends so the packaged
        # desktop runtime can store API keys in the system Keychain
        # instead of a plaintext local file. This lets dev and desktop
        # share config via the same Keychain entry.
        "--collect-all",
        "keyring",
        "--hidden-import",
        "keyring.backends.macOS",
        "--hidden-import",
        "keyring.backends.Windows",
        "--hidden-import",
        "keyring.backends.SecretService",
        "--hidden-import",
        "keyring.backends.chainer",
        "--hidden-import",
        "keyring.backends.fail",
        str(root / "backend" / "app" / "desktop_runtime.py"),
    ]
    if sys.platform == "darwin" and target_arch.strip():
        command.extend(["--target-arch", target_arch.strip()])
    subprocess.run(command, cwd=root, check=True)
    if not target_path.exists():
        raise SystemExit(f"Desktop sidecar build did not produce {target_path}")
    return target_path


def main() -> None:
    args = parse_args()
    built = build_sidecar(target_arch=args.target_arch)
    print(f"Built desktop sidecar: {built}")


if __name__ == "__main__":
    main()
