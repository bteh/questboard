"""Build the packaged desktop runtime sidecar for the current OS."""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
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
    return "questboard-runtime.exe" if sys.platform == "win32" else "questboard-runtime"


def tls_client_native_library(*, target_arch: str = "") -> Path:
    """Resolve the native library JobSpy imports through ``tls_client``.

    PyInstaller sees the Python package but cannot infer the filename assembled
    dynamically in ``tls_client.cffi``. Bundle only the current target's
    library instead of shipping ~80 MB of Windows, Linux, Intel, and Arm
    binaries in every desktop build.
    """
    spec = importlib.util.find_spec("tls_client")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit("tls_client is required by python-jobspy but is not installed")
    dependencies = Path(next(iter(spec.submodule_search_locations))) / "dependencies"
    arch = (target_arch or platform.machine()).strip().lower()
    if sys.platform == "darwin":
        filename = "tls-client-arm64.dylib" if arch in {"arm64", "aarch64"} else "tls-client-x86.dylib"
    elif sys.platform == "win32":
        filename = "tls-client-64.dll" if sys.maxsize > 2**32 else "tls-client-32.dll"
    elif arch in {"arm64", "aarch64"}:
        filename = "tls-client-arm64.so"
    elif "x86" in arch:
        filename = "tls-client-x86.so"
    else:
        filename = "tls-client-amd64.so"
    resolved = dependencies / filename
    if not resolved.exists():
        raise SystemExit(f"tls_client native library not found: {resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Questboard desktop sidecar")
    parser.add_argument(
        "--target-arch",
        default="",
        help="macOS target architecture for PyInstaller (x86_64, arm64, universal2)",
    )
    return parser.parse_args()


def reset_staging_dir(path: Path) -> None:
    """Empty the sidecar staging dir before staging a new build.

    tauri.conf.json bundles the whole ``tauri-sidecars/*`` glob, so any
    leftover file here (like the pre-rename launchboard-runtime) ships
    inside the DMG. Unlinking only the current target name is not enough.
    """
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def build_sidecar(*, target_arch: str = "") -> Path:
    root = repo_root()
    output_dir = sidecar_dir()
    work_dir = pyinstaller_work_dir()
    reset_staging_dir(output_dir)
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

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "questboard-runtime",
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
        # The API router and scraper registry both load modules dynamically.
        # Collect Python modules only: ``--collect-all job_finder`` would also
        # package ignored personal profile YAML files from a developer's
        # checkout, which is explicitly forbidden for a distributable build.
        "--collect-submodules",
        "app",
        "--collect-submodules",
        "job_finder",
        # JobSpy imports every board implementation from its package
        # initializer. Collecting it explicitly keeps that first main-thread
        # import stable as the library adds scraper modules between releases.
        "--collect-submodules",
        "jobspy",
        # Bundle the keyring library + OS backends so the packaged
        # desktop runtime can store API keys in the system Keychain
        # instead of a plaintext local file. This lets dev and desktop
        # share config via the same Keychain entry.
        "--collect-all",
        "keyring",
        "--collect-all",
        "mcp",
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

    # tls_client computes this path at runtime, so PyInstaller cannot discover
    # it through import analysis. Without the native file, JobSpy's first
    # import fails and Indeed/LinkedIn silently disappear from installed pulls.
    tls_library = tls_client_native_library(target_arch=target_arch)
    command.extend([
        "--add-binary",
        f"{tls_library}{os.pathsep}tls_client/dependencies",
    ])

    safe_data_files = [
        (root / "packages" / "kinds" / "kinds.json", "packages/kinds"),
        (root / "src" / "job_finder" / "config" / "search_config.yaml", "job_finder/config"),
        (
            root / "src" / "job_finder" / "config" / "profiles" / "_template.yaml",
            "job_finder/config/profiles",
        ),
    ]
    for data_file in sorted((root / "src" / "job_finder" / "config" / "archetypes").glob("*.yaml")):
        safe_data_files.append((data_file, "job_finder/config/archetypes"))
    for data_file in sorted((root / "src" / "job_finder" / "tools" / "scrapers" / "data").glob("*.txt")):
        safe_data_files.append((data_file, "job_finder/tools/scrapers/data"))
    for source, destination in safe_data_files:
        command.extend(["--add-data", f"{source}{os.pathsep}{destination}"])
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
