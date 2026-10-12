"""YC-backed companies, looked up by the public job board a posting lives on.

Most Find Work rows arrive with no headcount and no funding round, so the
classifier could only call a company a startup when it sat on a hand-kept
list. The bundled snapshot (config/startup_boards.json, rebuilt by
scripts/build_startup_boards.py) maps Ashby, Greenhouse and Lever boards to
the YC company that owns them. A board makes it into the snapshot only when
its own postings name that company or its website, so an exact board match
here is trusted without any name matching at read time.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(__file__).parent / "config" / "startup_boards.json"

_BOARD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ashby", re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)", re.I)),
    ("greenhouse", re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/embed/job_app\?(?:.*&)?for=([^&#]+)", re.I)),
    ("greenhouse", re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/(?!embed/)([^/?#]+)", re.I)),
    ("lever", re.compile(r"^https?://jobs\.lever\.co/([^/?#]+)", re.I)),
)

_SEASONS = {"winter": "W", "summer": "S", "spring": "X", "fall": "F"}


def board_for_url(url: str | None) -> tuple[str, str] | None:
    """("ashby", "trmlabs") for https://jobs.ashbyhq.com/trmlabs/..., else None."""
    for ats, pattern in _BOARD_PATTERNS:
        match = pattern.match(url or "")
        if match:
            return ats, match.group(1).lower()
    return None


@lru_cache(maxsize=1)
def _load_snapshot() -> tuple[str, dict[tuple[str, str], dict]]:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("startup board snapshot missing or unreadable at %s", SNAPSHOT_PATH)
        return "", {}
    boards = {
        (str(row["ats"]), str(row["slug"]).lower()): row
        for row in payload.get("boards") or []
        if row.get("ats") and row.get("slug")
    }
    return str(payload.get("built_at") or ""), boards


def _boards() -> dict[tuple[str, str], dict]:
    return _load_snapshot()[1]


def board_slugs(ats: str) -> list[str]:
    """Every YC board slug on one ATS, sorted, for the startup rotation lane."""
    return sorted(slug for host, slug in _boards() if host == ats)


def snapshot_version() -> int:
    """20261012 for a snapshot built 2026-10-12; 0 when none shipped."""
    digits = re.sub(r"\D", "", _load_snapshot()[0])
    return int(digits) if digits else 0


def _short_batch(batch: str) -> str:
    """"Summer 2019" -> "S19"; anything unexpected passes through."""
    parts = (batch or "").split()
    if len(parts) == 2 and parts[0].lower() in _SEASONS and parts[1].isdigit():
        return _SEASONS[parts[0].lower()] + parts[1][-2:]
    return batch or ""


def startup_stage_for_url(url: str | None) -> str | None:
    """A funding_stage string like "YC W19 (early)" for a YC company's board."""
    board = board_for_url(url)
    fact = _boards().get(board) if board else None
    if not fact:
        return None
    stage = "growth" if str(fact.get("stage")).lower() == "growth" else "early"
    batch = _short_batch(str(fact.get("batch") or ""))
    return f"YC {batch} ({stage})" if batch else f"YC ({stage})"
