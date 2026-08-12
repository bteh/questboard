"""JobSpy-powered job search — plain function, no framework dependency.

This module also implements a per-board **circuit breaker** around JobSpy.
The library's underlying scrapers (Indeed, Glassdoor, ZipRecruiter, Google,
LinkedIn) each fail in their own ways — 429 / 403 / Cloudflare CAPTCHA /
location parse errors. JobSpy doesn't ship a fail-fast mechanism: every
query that hits a broken board burns ~30 retries with backoff before
giving up, blocking the entire search for minutes.

The breaker watches the ``JobSpy`` logger family (each scraper logs under
``JobSpy:<Board>``) and counts ``ERROR``-level messages per board. Only
errors that CLUSTER within ``_FAILURE_WINDOW_S`` count: once ``_FAILURE_THRESHOLD``
land inside that rolling window the board goes "circuit-open" for
``_DISABLE_DURATION_S`` seconds and subsequent ``search_jobs`` calls skip it.
Isolated, spread-out transient errors expire instead of accumulating, so a
healthy board running under load doesn't get blacked out by the odd 429.
A board that returns ≥1 result in the response DataFrame resets its failure
counter immediately (self-healing once the upstream service recovers).

This is the production pattern that lets a flaky board (Google CAPTCHA,
Indeed throttling) self-heal: when it recovers the breaker closes and the
board comes back automatically. No human intervention, no permanent
hard-disable. Pair it with more than one working board so a single board's
open circuit never zeroes an entire run.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def preload_jobspy() -> str:
    """Import JobSpy on the caller's thread and return any import error.

    The desktop runtime starts searches on a worker thread.  In a frozen
    PyInstaller process, JobSpy's first import (including its Pydantic models
    and scraper modules) is not reliable when that first import happens in a
    worker: the exception used to escape before telemetry existed, making both
    Indeed and LinkedIn look as if they had never been attempted.  Desktop
    startup calls this once on the main thread.  Keeping the function public
    also gives the bundle verifier one small dependency health check without
    contacting a job board.

    Do not cache the callable here.  Tests and embedders intentionally replace
    ``sys.modules['jobspy']``; the ordinary search path should continue to
    resolve that module at call time.
    """
    try:
        from jobspy import scrape_jobs as _scrape_jobs  # noqa: F401
    except Exception as exc:  # ImportError is not the only frozen-import failure
        error = f"{type(exc).__name__}: {exc}"
        logger.error("JobSpy could not be imported: %s", error)
        return error
    return ""


# -- Per-board circuit breaker ---------------------------------------------

_FAILURE_THRESHOLD = 3
# Failures must CLUSTER within this rolling window to trip the breaker. A board
# logs the odd transient ERROR (a single 429, a flaky timeout) under normal load;
# without a window those isolated errors accumulate across a whole run — or even
# across runs, since this state is module-global — and eventually black out the
# board for no good reason. Expiring failures older than the window means only a
# genuine burst (threshold errors close together) opens the circuit.
_FAILURE_WINDOW_S = 120  # 2 minutes
_DISABLE_DURATION_S = 300  # 5 minutes — recover fast once the burst passes

# Module-level state. Keyed by lowercase board name.
# Each value: {"failures": int, "disabled_until": float, "window_start": float}.
_BOARD_CIRCUIT: dict[str, dict[str, Any]] = {}
_BOARD_CIRCUIT_LOCK = threading.Lock()


def _normalize_board(name: str) -> str:
    return (name or "").strip().lower()


def _is_board_disabled(name: str) -> bool:
    """True if the board's circuit is currently open."""
    with _BOARD_CIRCUIT_LOCK:
        state = _BOARD_CIRCUIT.get(_normalize_board(name))
        if not state:
            return False
        return time.time() < float(state.get("disabled_until", 0.0))


def _filter_active_boards(boards: list[str]) -> tuple[list[str], list[str]]:
    """Split a board list into (still-active, currently-disabled).

    Used so callers can log which boards got skipped this turn.
    """
    active, skipped = [], []
    for b in boards:
        if _is_board_disabled(b):
            skipped.append(b)
        else:
            active.append(b)
    return active, skipped


def _record_board_failure(board: str) -> None:
    """Increment failure count for a board; open the circuit at threshold."""
    key = _normalize_board(board)
    if not key:
        return
    now = time.time()
    with _BOARD_CIRCUIT_LOCK:
        state = _BOARD_CIRCUIT.setdefault(
            key, {"failures": 0, "disabled_until": 0.0, "window_start": now}
        )
        # Roll the failure window: if the current streak started more than
        # _FAILURE_WINDOW_S ago, the old errors have expired — restart the count
        # so only a fresh burst can trip the breaker.
        if state["failures"] == 0 or now - state.get("window_start", now) > _FAILURE_WINDOW_S:
            state["failures"] = 0
            state["window_start"] = now
        state["failures"] = int(state.get("failures", 0)) + 1
        if state["failures"] >= _FAILURE_THRESHOLD and now >= state["disabled_until"]:
            state["disabled_until"] = now + _DISABLE_DURATION_S
            logger.warning(
                "JobSpy circuit open for %s after %d errors in %ds — disabled for %ds",
                key, state["failures"], _FAILURE_WINDOW_S, _DISABLE_DURATION_S,
            )


def _record_board_success(boards: list[str], df: pd.DataFrame | None) -> None:
    """Reset failure counter for any board that returned ≥1 row.

    Self-healing: as soon as a board recovers, the breaker closes.
    """
    if df is None or df.empty:
        return
    try:
        sites_with_results = {
            _normalize_board(s) for s in df["site"].dropna().astype(str).tolist()
        }
    except (KeyError, AttributeError):
        return
    with _BOARD_CIRCUIT_LOCK:
        for board in boards:
            key = _normalize_board(board)
            if key in sites_with_results:
                _BOARD_CIRCUIT.pop(key, None)


def reset_circuit() -> None:
    """Test helper — wipe all circuit state."""
    with _BOARD_CIRCUIT_LOCK:
        _BOARD_CIRCUIT.clear()


class _JobSpyErrorHandler(logging.Handler):
    """Hooks the ``JobSpy:<Board>`` loggers and feeds the circuit breaker.

    JobSpy logs each scraper under ``JobSpy:Indeed``, ``JobSpy:Glassdoor``,
    etc. An ERROR-level message from one of those is the cleanest signal
    we get that a specific board is failing right now (429 / 403 / parse
    error / timeout).
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover — exercised via tests
        if record.levelno < logging.ERROR:
            return
        name = record.name or ""
        if not name.startswith("JobSpy:"):
            return
        board = name.split(":", 1)[1].strip()
        if board:
            _record_board_failure(board)


def _install_jobspy_error_handler() -> None:
    """Attach the handler to the root logger.

    JobSpy uses colon-separated logger names like ``JobSpy:Google``, which
    are NOT children of ``JobSpy`` in Python's dot-hierarchy — so a handler
    on ``logging.getLogger("JobSpy")`` would never see them. Attaching to
    the root logger + filtering by ``record.name`` inside ``_JobSpyErrorHandler``
    is the only reliable way to intercept these.

    Idempotent across module reloads (uvicorn --reload).
    """
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, _JobSpyErrorHandler):
            return
    root.addHandler(_JobSpyErrorHandler())


_install_jobspy_error_handler()


# -- Safe type helpers (pandas NaN handling) --------------------------------

def _safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string, handling NaN and None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value)


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_bool(value: Any) -> bool:
    """Safely convert to bool, treating NaN as False."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return bool(value)


# -- Main search function --------------------------------------------------

_DEFAULT_BOARDS = ["indeed", "glassdoor", "zip_recruiter", "google"]


def search_jobs(
    search_term: str,
    location: str = "United States",
    results_wanted: int = 25,
    hours_old: int = 336,
    is_remote: bool | None = None,
    country: str = "USA",
    linkedin_fetch_description: bool = True,
    boards: list[str] | None = None,
    distance: int | None = None,
    scrape_timeout: float | None = None,
    telemetry: dict[str, Any] | None = None,
) -> list[dict]:
    """Search multiple job boards via JobSpy and return normalised dicts.

    Returns a *list of dicts* (not JSON string) for direct Python consumption.
    Each dict has keys: title, company, location, url, source, description,
    salary_min, salary_max, date_posted, is_remote, company_size.

    Parameters
    ----------
    linkedin_fetch_description : bool
        Fetch full job page per LinkedIn result (~2-3s each).  The pipeline
        passes ``False`` during fast search and relies on descriptions from
        other boards.  CLI callers default to ``True`` for richer data.
    boards : list[str] or None
        JobSpy site names to scrape.  Defaults to Indeed, Glassdoor,
        ZipRecruiter, and Google. LinkedIn is opt-in via ``job_boards``.
    """
    started = time.monotonic()

    def _finish(reason: str, rows: int = 0, error: str = "") -> None:
        if telemetry is None:
            return
        telemetry.update({
            "finish_reason": reason,
            "rows_found": max(0, int(rows)),
            "duration_s": round(time.monotonic() - started, 3),
            "error_sample": str(error)[:500],
        })

    try:
        from jobspy import scrape_jobs
    except Exception as exc:
        # A frozen desktop import can fail with more than ImportError (for
        # example while a dependency initialises a model).  Always turn that
        # into source telemetry instead of letting the board disappear with
        # ``attempts: 0`` and no explanation.
        error = f"{type(exc).__name__}: {exc}"
        logger.error("python-jobspy could not be imported: %s", error)
        _finish("exception", error=error)
        return []

    requested_boards = list(boards or _DEFAULT_BOARDS)
    active_boards, skipped_boards = _filter_active_boards(requested_boards)
    if skipped_boards:
        logger.info(
            "JobSpy circuit-open boards skipped this call: %s",
            ", ".join(skipped_boards),
        )
    if not active_boards:
        # All requested boards are circuit-open. Returning [] saves the cost
        # of a doomed scrape_jobs call (which JobSpy would retry ~30× before
        # giving up).
        _finish(
            "exception",
            error=f"circuit open for {', '.join(skipped_boards) or 'requested boards'}",
        )
        return []
    site_names = active_boards

    # Google Jobs interprets "jobs near <location>" literally. For remote
    # searches or empty/wildcard locations, "near Remote" returns ~nothing.
    # Build a remote-aware query so Google contributes real volume.
    _loc = (location or "").strip().lower()
    _is_remote_query = is_remote is True or _loc in ("", "remote", "anywhere", "us", "usa", "united states")
    if _is_remote_query:
        google_search_term = f"remote {search_term} jobs"
    else:
        google_search_term = f"{search_term} jobs near {location}"

    try:
        scrape_kwargs = dict(
            site_name=site_names,
            search_term=search_term,
            google_search_term=google_search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country,
            linkedin_fetch_description=linkedin_fetch_description,
        )
        # Only pass is_remote when explicitly True/False (not None)
        # JobSpy Pydantic model rejects None
        if is_remote is not None:
            scrape_kwargs["is_remote"] = bool(is_remote)
        if distance is not None:
            scrape_kwargs["distance"] = distance

        # Bound the scrape with a wall-clock deadline when requested. JobSpy
        # has no fail-fast knob, so a slow/hung board (google CAPTCHA, Indeed
        # 429-with-backoff) blocks for minutes. We run scrape_jobs on a DAEMON
        # thread and stop waiting after ``scrape_timeout`` seconds, feeding the
        # breaker so the board is skipped on subsequent calls. The thread must
        # be a daemon (not a ThreadPoolExecutor worker) so an abandoned hung
        # scrape dies with the process instead of blocking interpreter exit via
        # CPython's atexit join — otherwise the multi-minute stall would just be
        # deferred to shutdown (a real hazard on the one-shot CLI path).
        if scrape_timeout is not None and scrape_timeout > 0:
            _scrape_result: dict[str, Any] = {}

            def _bounded_scrape() -> None:
                try:
                    _scrape_result["df"] = scrape_jobs(**scrape_kwargs)
                except Exception as exc:  # surfaced to the outer handler below
                    _scrape_result["exc"] = exc

            _t = threading.Thread(target=_bounded_scrape, name="jobspy-scrape", daemon=True)
            _t.start()
            _t.join(timeout=scrape_timeout)
            if _t.is_alive():
                logger.warning(
                    "JobSpy scrape exceeded %.0fs for %s — abandoning; "
                    "opening breaker (orphaned daemon scrape drains in background)",
                    scrape_timeout, ", ".join(site_names),
                )
                for b in active_boards:
                    _record_board_failure(b)
                _finish(
                    "timeout",
                    error=f"scrape exceeded {scrape_timeout:.0f}s for {', '.join(site_names)}",
                )
                return []
            if "exc" in _scrape_result:
                raise _scrape_result["exc"]  # let the outer except log + return []
            jobs_df = _scrape_result["df"]
        else:
            jobs_df = scrape_jobs(**scrape_kwargs)

        # Self-healing: a board that returned ≥1 row in this call is clearly
        # working again, so reset its failure counter even if it had been
        # incrementing previously.
        _record_board_success(active_boards, jobs_df)

        if jobs_df.empty:
            _finish("zero_rows")
            return []

        jobs_list: list[dict] = []
        for _, row in jobs_df.iterrows():
            # Handle URL fallback properly (pandas NaN)
            url = row.get("job_url")
            if pd.isna(url) or not url:
                url = row.get("job_url_direct", "")

            loc_str = _safe_str(row.get("location", ""))
            loc_lower = loc_str.lower()
            raw_remote = _safe_bool(row.get("is_remote"))

            # Fix is_remote: hybrid jobs are NOT remote
            if any(kw in loc_lower for kw in ("hybrid", "in-office", "on-site")):
                is_remote_val = False
            elif raw_remote or "remote" in loc_lower:
                is_remote_val = True
            else:
                is_remote_val = False

            job = {
                "title": _safe_str(row.get("title", "")),
                "company": _safe_str(
                    row.get("company_name", row.get("company", ""))
                ),
                "location": loc_str,
                "url": _safe_str(url),
                "source": _safe_str(row.get("site", "")),
                "description": _safe_str(row.get("description", ""))[:3000],
                "salary_min": _safe_float(row.get("min_amount")),
                "salary_max": _safe_float(row.get("max_amount")),
                "date_posted": _safe_str(row.get("date_posted", "")),
                "is_remote": is_remote_val,
                "company_size": _safe_str(
                    row.get("company_num_employees", "")
                ),
            }
            # Capture JobSpy's pay interval (yearly/monthly/weekly/daily/hourly)
            # so salary scoring + the salary floor filter can annualize instead
            # of treating an $80/hr listing as an $80 salary.
            interval = _safe_str(row.get("interval", "")).strip().lower()
            job["salary_period"] = interval
            job["salary_currency"] = _safe_str(row.get("currency", ""))
            if interval:
                from job_finder.scoring.helpers import annualize_amount
                job["salary_min_annualized"] = annualize_amount(job["salary_min"], interval)
                job["salary_max_annualized"] = annualize_amount(job["salary_max"], interval)
            jobs_list.append(job)

        _finish("ok", rows=len(jobs_list))
        return jobs_list

    except Exception as e:
        logger.error("Job search failed for '%s' in %s: %s", search_term, location, e)
        _finish("exception", error=str(e))
        return []
