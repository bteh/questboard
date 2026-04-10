#!/usr/bin/env python3
"""Launchboard doctor — single command health check.

Run with `make doctor` or `python3 scripts/doctor.py`. Designed to be useful
to a non-technical user trying to figure out why their search isn't returning
results, AND useful to a contributor diagnosing a broken venv.

Checks (in order):

  1. Python version sane                  (>= 3.10)
  2. Virtualenv exists and is bootable    (.venv/bin/python --version)
  3. Repo deps installed                  (import job_finder, app)
  4. Backend & frontend DB files reachable (and exist)
  5. SQLite WAL mode enabled              (PRAGMA journal_mode)
  6. Database schema is up to date        (compares ORM columns to DB columns)
  7. Scrapers import without errors       (import each plugin module)
  8. LLM provider config is valid         (only if configured — no network call)
  9. Recent search activity               (any application row from last 14 days)
 10. Demo / test fixtures detected        (warns if [DEMO STUB] rows exist)

Output is a single colored PASS/WARN/FAIL list. Exit code 0 unless any FAIL.
WARNs do not fail the run — they're informational.

This is the kind of thing a non-technical user can run and copy-paste the
output into an issue. It's also the kind of thing CI can run as a smoke check.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# ── ANSI color helpers ────────────────────────────────────────────────────

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return _c("32", text)


def yellow(text: str) -> str:
    return _c("33", text)


def red(text: str) -> str:
    return _c("31", text)


def dim(text: str) -> str:
    return _c("2", text)


def bold(text: str) -> str:
    return _c("1", text)


# ── Result wiring ─────────────────────────────────────────────────────────

PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / WARN / FAIL
    message: str
    hint: str = ""


@dataclass
class Doctor:
    repo: Path
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, message: str, hint: str = "") -> None:
        self.results.append(CheckResult(name=name, status=status, message=message, hint=hint))

    def run(self, name: str, fn: Callable[[], tuple[str, str, str]]) -> None:
        try:
            status, message, hint = fn()
        except Exception as exc:  # noqa: BLE001
            self.add(name, FAIL, f"check raised {type(exc).__name__}: {exc}")
            return
        self.add(name, status, message, hint)

    @property
    def has_failures(self) -> bool:
        return any(r.status == FAIL for r in self.results)

    def render(self) -> None:
        widths = max(len(r.name) for r in self.results) + 2
        for r in self.results:
            badge = {
                PASS: green("PASS"),
                WARN: yellow("WARN"),
                FAIL: red("FAIL"),
            }[r.status]
            name = bold(r.name.ljust(widths))
            print(f"  {badge}  {name}  {r.message}")
            if r.hint:
                print(f"          {dim(r.hint)}")
        print()
        passes = sum(1 for r in self.results if r.status == PASS)
        warns = sum(1 for r in self.results if r.status == WARN)
        fails = sum(1 for r in self.results if r.status == FAIL)
        summary = f"  {green(f'{passes} passed')}, {yellow(f'{warns} warned')}, {red(f'{fails} failed')}"
        print(summary)
        print()
        if self.has_failures:
            print(red("  Doctor found problems. See FAIL items above for hints."))
        elif warns:
            print(yellow("  Launchboard is healthy. A few warnings worth reviewing above."))
        else:
            print(green("  Launchboard is healthy. All checks passed."))
        print()


# ── Individual checks ─────────────────────────────────────────────────────


def check_python_version() -> tuple[str, str, str]:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}"
    if (major, minor) < (3, 10):
        return FAIL, f"Python {version} (need >= 3.10)", "Install Python 3.10+ from https://python.org"
    return PASS, f"Python {version}", ""


def check_venv(repo: Path) -> tuple[str, str, str]:
    venv_python = repo / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return (
            FAIL,
            ".venv missing",
            "Run `make setup` or `python3 -m venv .venv && .venv/bin/pip install -e .`",
        )
    try:
        out = subprocess.run(
            [str(venv_python), "--version"], capture_output=True, text=True, timeout=5
        )
    except Exception as exc:  # noqa: BLE001
        return FAIL, f".venv/bin/python failed: {exc}", "The venv is corrupted. Recreate it with `make setup`."
    if out.returncode != 0:
        return (
            FAIL,
            f".venv/bin/python returned {out.returncode}",
            "Recreate the venv with `make setup`. The interpreter path may point at a moved Python.",
        )
    return PASS, out.stdout.strip() or out.stderr.strip(), ""


def check_imports(repo: Path) -> tuple[str, str, str]:
    venv_python = repo / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return WARN, "skipped — venv missing", ""
    code = (
        "import sys, pathlib;"
        f"sys.path.insert(0, str(pathlib.Path({str(repo / 'src')!r}).resolve()));"
        "from job_finder.models.schemas import EvaluationReport;"
        "from job_finder.tools.scrapers._registry import get_registry;"
        "import app.main;"
        "print(len(get_registry()))"
    )
    out = subprocess.run([str(venv_python), "-c", code], capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        return FAIL, "core imports failed", (out.stderr or out.stdout).strip()[:300]
    n = out.stdout.strip()
    return PASS, f"imports clean ({n} scrapers registered)", ""


def _db_paths(repo: Path) -> list[Path]:
    """All SQLite DB files Launchboard can be reading from."""
    candidates = [
        repo / "backend" / "data" / "job_tracker.db",
        repo / "data" / "job_tracker.db",
        repo / "data" / "dev-hosted" / "job_tracker.db",
    ]
    return [p for p in candidates if p.exists()]


def check_db_files(repo: Path) -> tuple[str, str, str]:
    found = _db_paths(repo)
    if not found:
        return WARN, "no DB files found yet", "First run will create them. Open the app and try a search."
    desc = ", ".join(str(p.relative_to(repo)) for p in found)
    return PASS, f"{len(found)} DB file(s) — {desc}", ""


def check_wal_mode(repo: Path) -> tuple[str, str, str]:
    import sqlite3

    found = _db_paths(repo)
    if not found:
        return WARN, "no DB to check", ""
    bad: list[str] = []
    for db in found:
        conn = sqlite3.connect(str(db))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        finally:
            conn.close()
        if mode != "wal":
            bad.append(f"{db.name}={mode}")
    if bad:
        return (
            WARN,
            f"WAL not enabled on: {', '.join(bad)}",
            "WAL is set on next backend boot. Restart the backend to apply.",
        )
    return PASS, f"WAL enabled on all {len(found)} DB(s)", ""


def check_db_schema(repo: Path) -> tuple[str, str, str]:
    import sqlite3

    venv_python = repo / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return WARN, "skipped — venv missing", ""
    found = _db_paths(repo)
    if not found:
        return WARN, "skipped — no DB", ""

    code = (
        "import sys, pathlib;"
        f"sys.path.insert(0, str(pathlib.Path({str(repo / 'src')!r}).resolve()));"
        "from job_finder.models.database import ApplicationRecord;"
        "print(','.join(c.name for c in ApplicationRecord.__table__.columns))"
    )
    out = subprocess.run([str(venv_python), "-c", code], capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        return FAIL, "could not introspect ORM", (out.stderr or out.stdout).strip()[:300]
    expected = set(out.stdout.strip().split(","))

    issues: list[str] = []
    for db in found:
        conn = sqlite3.connect(str(db))
        try:
            actual = {row[1] for row in conn.execute("PRAGMA table_info(applications)")}
        finally:
            conn.close()
        missing = sorted(expected - actual)
        if missing:
            issues.append(f"{db.name} missing: {', '.join(missing)}")
    if issues:
        return (
            FAIL,
            "ORM ↔ DB columns mismatch",
            "; ".join(issues) + " — restart the backend to run migrations",
        )
    return PASS, f"schema up to date on all {len(found)} DB(s)", ""


def check_scrapers(repo: Path) -> tuple[str, str, str]:
    venv_python = repo / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return WARN, "skipped — venv missing", ""
    code = (
        "import sys, pathlib;"
        f"sys.path.insert(0, str(pathlib.Path({str(repo / 'src')!r}).resolve()));"
        "from job_finder.tools.scrapers._registry import get_registry;"
        "print(len([m for m in get_registry().values() if m.search_fn is not None]))"
    )
    out = subprocess.run([str(venv_python), "-c", code], capture_output=True, text=True, timeout=15)
    if out.returncode != 0:
        return FAIL, "scraper imports failed", (out.stderr or out.stdout).strip()[:300]
    return PASS, f"{out.stdout.strip()} runnable scrapers loaded", ""


def check_llm_config(repo: Path) -> tuple[str, str, str]:
    venv_python = repo / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return WARN, "skipped — venv missing", ""
    code = (
        "import sys, pathlib, os;"
        f"sys.path.insert(0, str(pathlib.Path({str(repo / 'src')!r}).resolve()));"
        "from job_finder.llm_client import LLMClient;"
        "c = LLMClient();"
        "print('configured' if c.is_configured else 'unconfigured', '|', c.provider or '-', '|', c.model or '-')"
    )
    out = subprocess.run([str(venv_python), "-c", code], capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        return WARN, "could not check LLM client", (out.stderr or out.stdout).strip()[:300]
    line = out.stdout.strip()
    state, provider, model = [s.strip() for s in line.split("|")]
    if state == "unconfigured":
        return (
            WARN,
            "no LLM configured",
            "Launchboard works without AI but ranking is keyword-only. Connect a provider in Settings → AI.",
        )
    return PASS, f"LLM ready ({provider}, {model})", ""


def check_recent_activity(repo: Path) -> tuple[str, str, str]:
    import sqlite3

    found = _db_paths(repo)
    if not found:
        return WARN, "skipped — no DB", ""

    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).replace(tzinfo=None).isoformat()
    total = 0
    for db in found:
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE created_at IS NULL OR created_at >= ?",
                (cutoff,),
            ).fetchone()
            total += int(row[0] or 0)
        except sqlite3.OperationalError:
            # Table missing — first-run path
            continue
        finally:
            conn.close()
    if total == 0:
        return WARN, "no application rows in the last 14 days", "Run a search from the app to populate."
    return PASS, f"{total} application rows in the last 14 days", ""


def check_demo_fixtures(repo: Path) -> tuple[str, str, str]:
    import sqlite3

    found = _db_paths(repo)
    if not found:
        return PASS, "no DB to scan", ""
    stale = 0
    for db in found:
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE source = 'demo'"
            ).fetchone()
            stale += int(row[0] or 0)
        except sqlite3.OperationalError:
            continue
        finally:
            conn.close()
    if stale:
        return (
            WARN,
            f"{stale} demo / test fixture rows present",
            "Clean up with `sqlite3 backend/data/job_tracker.db \"DELETE FROM applications WHERE source = 'demo'\"`",
        )
    return PASS, "no demo fixtures detected", ""


# ── Entry point ───────────────────────────────────────────────────────────


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    print()
    print(bold("  Launchboard doctor"))
    print(dim(f"  repo: {repo}"))
    print()

    doc = Doctor(repo=repo)
    doc.run("python", check_python_version)
    doc.run("venv", lambda: check_venv(repo))
    doc.run("imports", lambda: check_imports(repo))
    doc.run("db files", lambda: check_db_files(repo))
    doc.run("db wal", lambda: check_wal_mode(repo))
    doc.run("db schema", lambda: check_db_schema(repo))
    doc.run("scrapers", lambda: check_scrapers(repo))
    doc.run("llm", lambda: check_llm_config(repo))
    doc.run("activity", lambda: check_recent_activity(repo))
    doc.run("fixtures", lambda: check_demo_fixtures(repo))

    doc.render()
    return 1 if doc.has_failures else 0


if __name__ == "__main__":
    # Make sure shutil is referenced — used historically; keep for future PATH lookups
    _ = shutil.which
    sys.exit(main())
