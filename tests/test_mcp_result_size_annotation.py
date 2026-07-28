"""The retrieval tools declare how large their results can legitimately be.

Claude Code caps an MCP tool result at 25,000 tokens by default and warns past
10,000; anything larger is written to a file and replaced with a reference the
model then has to go read. That is exactly what cost a `find_and_rank` run on
2026-07-24: `search_work` returned 84,647 characters (~25.6k tokens), the CLI
refused it four times, and the assistant burned the rest of the run shelling
out to `jq` instead of ranking.

Trimming the payload (tests/test_mcp_result_size.py) got a full page back under
the cap with room to spare, and that is still worth having — smaller results
are cheaper and faster to read. But the cliff itself is what made a page of
search results fail, and a board that keeps growing would eventually walk back
into it. `anthropic/maxResultSizeChars` in the tool's `tools/list` entry raises
the threshold for that tool alone, up to a documented ceiling of 500,000
characters, and applies whether or not anyone sets MAX_MCP_OUTPUT_TOKENS.

Only the two retrieval tools carry it. A tool that returns one row has no
business declaring a large result, and the annotation is a claim about what
the tool legitimately needs, not a blanket opt-out.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

# Documented hard ceiling; a larger value is silently clamped, so asking for
# more than this is a claim the client will not honor.
MAX_ALLOWED = 500_000


@pytest.fixture()
def tools(tmp_path, monkeypatch):
    """Resolve the server at test time; other tests swap app.* out of
    sys.modules and a module-level import would bind a stale object."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.local_mcp import mcp

    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def _limit(tool) -> int | None:
    meta = getattr(tool, "meta", None) or {}
    return meta.get("anthropic/maxResultSizeChars")


def test_search_work_declares_room_for_a_full_page(tools):
    assert _limit(tools["search_work"]), (
        "search_work returns a whole page of candidates; without the annotation "
        "a large page is written to a file instead of returned"
    )


def test_side_quest_search_declares_it_too(tools):
    """Same payload shape, same page size, same cliff."""
    assert _limit(tools["search_side_quests"])


def test_declared_limits_stay_under_the_documented_ceiling(tools):
    for name, tool in tools.items():
        limit = _limit(tool)
        if limit is not None:
            assert 0 < limit <= MAX_ALLOWED, f"{name} declares {limit}"


def test_single_row_tools_declare_nothing(tools):
    """The annotation says 'this tool legitimately returns a lot'. A tool that
    returns one opportunity does not, and shouldn't opt out of the cap."""
    for name in ("get_opportunity", "get_refresh_status", "server_info"):
        assert _limit(tools[name]) is None, f"{name} should not declare a size"


def test_the_annotation_reaches_the_wire_as_underscore_meta(tools):
    """Claude Code reads `_meta` on the tools/list entry. An attribute the
    server keeps to itself does nothing."""
    dumped = tools["search_work"].model_dump(by_alias=True, exclude_none=True)
    assert dumped["_meta"]["anthropic/maxResultSizeChars"] == _limit(tools["search_work"])
    # It has to survive JSON serialization too, not just model_dump.
    assert "anthropic/maxResultSizeChars" in json.dumps(dumped)


def test_the_declared_size_covers_a_real_full_page(tools):
    """The number has to be big enough for the payload it exists to protect,
    with headroom for the board to grow."""
    from app.services.local_agent_service import _MCP_RESULT_CHAR_BUDGET

    assert _limit(tools["search_work"]) >= _MCP_RESULT_CHAR_BUDGET * 2
