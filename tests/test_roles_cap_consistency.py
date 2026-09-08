"""set_career_preferences advertises an 18-role cap (ROLES_CAP); the save
layer must honor the same number.

Bug: save_workspace_preferences trimmed roles to a hardcoded 15, so a save
of 16-18 roles reported saved=True while silently dropping the tail. Brian
hit this adding startup-convention titles (Head of Data, Lead Data
Engineer) as roles 16-19: the tool said saved, the board never changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

# pytest puts tests/ itself on sys.path (rootdir import mode), so the bare
# module name works under both `pytest` and `python -m pytest`; `tests.` only
# resolves when the cwd happens to be on sys.path.
from test_local_agent_service import local_agent_db  # noqa: F401


def test_save_honors_the_full_advertised_roles_cap(local_agent_db) -> None:  # noqa: F811
    from app.services import local_agent_service

    roles = [f"Role {i:02d}" for i in range(1, local_agent_service.ROLES_CAP + 1)]
    result = local_agent_service.set_career_preferences(local_agent_db, roles=roles)
    assert result["saved"] is True

    saved = local_agent_service.career_preferences(local_agent_db)["preferences"]["roles"]
    assert saved == roles, (
        f"saved {len(saved)} of {len(roles)} roles: the save layer is "
        "trimming below ROLES_CAP after reporting saved=True"
    )


def test_over_cap_save_keeps_the_first_cap_roles(local_agent_db) -> None:  # noqa: F811
    from app.services import local_agent_service

    cap = local_agent_service.ROLES_CAP
    roles = [f"Role {i:02d}" for i in range(1, cap + 4)]
    local_agent_service.set_career_preferences(local_agent_db, roles=roles)

    saved = local_agent_service.career_preferences(local_agent_db)["preferences"]["roles"]
    assert saved == roles[:cap]
