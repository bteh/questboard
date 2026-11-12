"""Find the ATS board of a board company the catalog can't name.

Nov 12 2026: Trella Health reached the board through LinkedIn, but its name is
in no catalog, seed, or verified list, so resolve_watchlist said "unknown" and
boards.greenhouse.io/trellahealth (live "Data Engineering Manager") was never
scanned. Most ATS slugs are the squashed company name, so an unknown name is
asked of each host once, and the answer (board or no board) is remembered for
``MEMO_TTL_DAYS``. A found board is also promoted into that host's discovered
cache, which runs every pull outside the per-host cap on board companies.

Probing happens before the scrapers start, outside their 100s deadline, so it
is bounded twice: at most ``MAX_NEW_NAMES_PER_PULL`` new names per pull, and
``PROBE_DEADLINE_SECONDS`` of wall clock no matter how the hosts behave.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from job_finder.config.company_catalog import _VERIFIED_HOSTS, _verified_key

logger = logging.getLogger(__name__)

MEMO_TTL_DAYS = 14
MAX_NEW_NAMES_PER_PULL = 40
PROBE_DEADLINE_SECONDS = 8.0
PROBE_WORKERS = 8
MIN_SLUG_LEN = 3

ProbeFor = Callable[[str], Callable[[str], "int | None"]]

_MEMO_LOCK = threading.Lock()


def _default_probe_for(host: str) -> Callable[[str], int | None]:
    # Looked up per call so a test's monkeypatch of probe_status is honored.
    from job_finder.tools.scrapers import _board_probe

    return _board_probe.probe_status(host)


def _default_promote(host: str, slugs: set[str]) -> int:
    from job_finder.tools.scrapers._ats_discovery import promote_slugs

    return promote_slugs(host, slugs)


def _memo_path() -> Path:
    # Read at call time: tests point _CACHE_DIR at a temp dir per test.
    from job_finder.tools.scrapers import _ats_discovery

    return _ats_discovery._CACHE_DIR / "board_name_probes.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_memo() -> dict[str, dict[str, str]]:
    """Unexpired probe answers by squashed name; a miss has no ``ats``."""
    path = _memo_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    names = payload.get("names") if isinstance(payload, dict) else None
    if not isinstance(names, dict):
        return {}
    cutoff = _now() - timedelta(days=MEMO_TTL_DAYS)
    fresh: dict[str, dict[str, str]] = {}
    for key, entry in names.items():
        try:
            checked = datetime.fromisoformat(str(entry.get("checked_at", "")))
        except (AttributeError, TypeError, ValueError):
            continue
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        if checked >= cutoff:
            fresh[str(key)] = entry
    return fresh


def _save_memo(memo: dict[str, dict[str, str]]) -> None:
    path = _memo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp",
    ) as tmp:
        json.dump({"version": 1, "names": memo}, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _probe_names(
    keys: list[str], probe_for: ProbeFor,
) -> dict[str, dict[str, int | None]]:
    """Status per host per key for every probe that answered before the deadline."""
    probes = {host: probe_for(host) for host in _VERIFIED_HOSTS}
    answers: dict[str, dict[str, int | None]] = {key: {} for key in keys}
    pool = ThreadPoolExecutor(max_workers=PROBE_WORKERS, thread_name_prefix="board-probe")
    futures = {
        pool.submit(probes[host], key): (key, host) for key in keys for host in _VERIFIED_HOSTS
    }
    done, _pending = wait(futures, timeout=PROBE_DEADLINE_SECONDS)
    # Unfinished probes are abandoned, not awaited: the pull goes on.
    pool.shutdown(wait=False, cancel_futures=True)
    for future in done:
        key, host = futures[future]
        try:
            answers[key][host] = future.result()
        except Exception:
            answers[key][host] = None
    return answers


def _verdict(statuses: dict[str, int | None]) -> dict[str, str] | None:
    """Board (first host in verified-list order wins), miss, or None for ask again."""
    for host in _VERIFIED_HOSTS:
        if statuses.get(host) == 200:
            return {"ats": host}
    complete = len(statuses) == len(_VERIFIED_HOSTS)
    if complete and all(status is not None for status in statuses.values()):
        return {}
    # A timeout or refusal is a host having a bad minute, not proof of no board.
    return None


def boards_for_unresolved(
    entries: list[dict[str, str]],
    *,
    probe_for: ProbeFor = _default_probe_for,
    promote: Callable[[str, set[str]], int] = _default_promote,
    priority: list[str] | None = None,
) -> list[dict[str, str]]:
    """Fill in ats/slug for unknown entries from the memo or a bounded probe.

    ``priority`` (company names, best first) picks which unknown names spend
    this pull's probe budget; names it lacks follow in entry order. Order of
    the returned entries is kept. Entries still unknown are returned as given.
    Never raises: a probe or cache failure leaves the entries unresolved.
    """
    try:
        return _fill(entries, probe_for, promote, priority)
    except Exception as exc:
        logger.warning("Board name probe failed (non-fatal): %s", exc)
        return list(entries)


def _fill(entries, probe_for, promote, priority):
    unknown_keys: list[str] = []
    for entry in entries:
        if entry.get("ats", "unknown") != "unknown":
            continue
        key = _verified_key(entry.get("name", ""))
        if len(key) >= MIN_SLUG_LEN and key not in unknown_keys:
            unknown_keys.append(key)
    if not unknown_keys:
        return list(entries)

    with _MEMO_LOCK:
        memo = load_memo()
        to_probe = [k for k in unknown_keys if k not in memo]
        if priority:
            rank: dict[str, int] = {}
            for i, name in enumerate(priority):
                rank.setdefault(_verified_key(name), i)
            # sorted() is stable, so unranked names keep entry order after the ranked.
            to_probe.sort(key=lambda k: rank.get(k, len(rank)))
        to_probe = to_probe[:MAX_NEW_NAMES_PER_PULL]
        if to_probe:
            stamp = _now().isoformat()
            found: dict[str, set[str]] = {}
            for key, statuses in _probe_names(to_probe, probe_for).items():
                verdict = _verdict(statuses)
                if verdict is None:
                    continue
                if verdict:
                    verdict["slug"] = key
                    found.setdefault(verdict["ats"], set()).add(key)
                memo[key] = {**verdict, "checked_at": stamp}
            _save_memo(memo)
            for host, slugs in found.items():
                promote(host, slugs)
            if found:
                logger.info(
                    "Board name probe: found %d board(s) for unresolved board companies",
                    sum(len(s) for s in found.values()),
                )

    out = []
    for entry in entries:
        hit = memo.get(_verified_key(entry.get("name", "")))
        if entry.get("ats", "unknown") == "unknown" and hit and hit.get("ats"):
            out.append({"name": entry["name"], "ats": hit["ats"], "slug": hit["slug"]})
        else:
            out.append(entry)
    return out
