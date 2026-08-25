"""Verify packaged desktop artifacts for structural correctness."""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Questboard desktop bundle")
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


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> dict:
    request = urllib.request.Request(
        url,
        method=method,
        headers=headers or {},
        data=b"" if method != "GET" else None,
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object response from {url}")
    return payload


def smoke_packaged_runtime(sidecar: Path) -> None:
    """Boot the shipped sidecar exactly like a clean friend's machine."""
    port = _available_port()
    with tempfile.TemporaryDirectory(prefix="questboard-friend-smoke-") as temp:
        root = Path(temp)
        env = os.environ.copy()
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "DATABASE_URL",
            "JOB_FINDER_DATABASE_URL",
            "DATA_DIR",
            "CONFIG_DIR",
            "RESUME_DIR",
            "WORKSPACE_STORAGE_DIR",
            "HOSTED_MODE",
            "QUESTBOARD_DESKTOP_RUNTIME",
        ):
            env.pop(key, None)
        shared_args = [
            "--data-dir",
            str(root / "data"),
            "--workspace-storage-dir",
            str(root / "data" / "workspaces"),
            "--resume-dir",
            str(root / "knowledge"),
            "--config-dir",
            str(root / "config"),
            "--dev-origin",
            "http://127.0.0.1:5173",
        ]
        jobspy_check = subprocess.run(
            [str(sidecar), *shared_args, "--check-jobspy-import"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
        )
        if jobspy_check.returncode != 0:
            raise RuntimeError(
                "Packaged runtime cannot import JobSpy:\n"
                + (jobspy_check.stdout + jobspy_check.stderr)[-4000:]
            )
        process = subprocess.Popen(
            [
                str(sidecar),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                *shared_args,
            ],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=os.name != "nt",
        )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise RuntimeError(
                        "Packaged runtime exited during clean-machine smoke test:\n"
                        + output[-4000:]
                    )
                try:
                    health = _json_request(f"{base}/health")
                    if health.get("status") == "ok":
                        break
                except (OSError, urllib.error.URLError, ValueError):
                    time.sleep(0.25)
            else:
                raise RuntimeError("Packaged runtime did not become healthy within 75 seconds")

            bootstrap = _json_request(f"{base}/api/v1/session/bootstrap", method="POST")
            session_token = str(bootstrap.get("session_token") or "")
            if not session_token:
                raise RuntimeError("Fresh desktop bootstrap returned no local session token")
            session_headers = {"X-Questboard-Session": session_token}
            defaults = _json_request(
                f"{base}/api/v1/search/defaults",
                headers=session_headers,
            )
            onboarding = _json_request(
                f"{base}/api/v1/onboarding/state",
                headers=session_headers,
            )
            expected_blank = {
                "roles": [],
                "keywords": [],
                "locations": [],
                "current_title": "",
                "current_level": "",
                "min_base": None,
                "target_total_comp": None,
            }
            actual_blank = {key: defaults.get(key) for key in expected_blank}
            if actual_blank != expected_blank:
                raise RuntimeError(
                    "Fresh install inherited non-neutral search defaults: "
                    + json.dumps(actual_blank, sort_keys=True)
                )
            if not onboarding.get("needs_resume") or not onboarding.get("needs_preferences"):
                raise RuntimeError("Fresh install did not open in blank onboarding state")
            if onboarding.get("ready_to_search"):
                raise RuntimeError("Fresh install incorrectly reported itself ready to search")
        finally:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait(timeout=5)


_ALLOWED_SIDECAR_NAMES = {"questboard-runtime", "questboard-runtime.exe"}


def unexpected_sidecar_files(sidecars_dir: Path) -> list[Path]:
    """Anything staged next to the runtime ships in the DMG, so a stray
    file here (a stale launchboard-runtime, a test binary) is a packaging
    failure, not noise."""
    if not sidecars_dir.exists():
        return []
    return sorted(
        path for path in sidecars_dir.iterdir() if path.name not in _ALLOWED_SIDECAR_NAMES
    )


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
    app_bundle = bundle_root / "macos" / "Questboard.app"
    app_binary = app_bundle / "Contents" / "MacOS" / "questboard-desktop"
    sidecar = app_bundle / "Contents" / "Resources" / "sidecars" / "questboard-runtime"
    dmg_dir = bundle_root / "dmg"

    if not app_binary.exists():
        raise SystemExit(f"Missing app binary: {app_binary}")
    if not sidecar.exists():
        raise SystemExit(f"Missing packaged sidecar: {sidecar}")
    if not dmg_dir.exists():
        raise SystemExit(f"Missing DMG output directory: {dmg_dir}")

    strays = unexpected_sidecar_files(sidecar.parent)
    if strays:
        raise SystemExit(
            "Desktop bundle ships unexpected sidecar files: "
            + ", ".join(path.name for path in strays)
        )

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

    forbidden_suffixes = {".db", ".sqlite", ".pdf", ".docx", ".env", ".yaml", ".yml"}
    forbidden_files = [
        path for path in app_bundle.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes
    ]
    if forbidden_files:
        raise SystemExit(
            "Desktop bundle contains user/config data files: "
            + ", ".join(str(path.relative_to(app_bundle)) for path in forbidden_files)
        )

    smoke_packaged_runtime(sidecar)


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
