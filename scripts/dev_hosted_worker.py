from __future__ import annotations

import os
import sys
from pathlib import Path

from watchfiles import PythonFilter, run_process


def _run_worker(backend_dir: str, src_dir: str) -> None:
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.chdir(backend_dir)

    from app.worker import main as worker_main

    try:
        worker_main()
    except KeyboardInterrupt:
        return


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    backend_dir = repo_root / "backend"
    src_dir = repo_root / "src"

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_dir) if not existing_pythonpath else f"{src_dir}:{existing_pythonpath}"
    os.environ.update(env)

    return run_process(
        str(backend_dir),
        str(src_dir),
        target=_run_worker,
        args=(str(backend_dir), str(src_dir)),
        target_type="function",
        watch_filter=PythonFilter(),
        grace_period=0.2,
        sigint_timeout=5,
        sigkill_timeout=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
