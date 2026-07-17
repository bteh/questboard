"""Grant, revoke, or show local resume-access consent (human-run only).

The connected agent can never call this: a person runs it in a terminal, or the
Questboard app calls resume_consent.grant/revoke behind a Settings toggle. This
is what makes read_resume_for_matching's "only after explicit permission" real.

    python scripts/resume_consent.py grant          # allow agent to read resume
    python scripts/resume_consent.py grant --ttl-hours 24
    python scripts/resume_consent.py revoke
    python scripts/resume_consent.py status
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "backend", ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def main() -> int:
    parser = argparse.ArgumentParser(description="Local resume consent for the agent integration")
    parser.add_argument("action", choices=["grant", "revoke", "status"])
    parser.add_argument(
        "--data-dir",
        default=os.getenv("QUESTBOARD_DATA_DIR", str(ROOT / "backend" / "data")),
        help="Questboard data directory (must match the MCP server's --data-dir)",
    )
    parser.add_argument("--ttl-hours", type=int, default=None, help="Optional expiry in hours")
    args = parser.parse_args()

    from app.local_mcp import configure_environment
    from app.models.database import get_db, init_db
    from app.services import local_agent_service, resume_consent

    configure_environment(Path(args.data_dir))
    init_db()

    generator = get_db()
    db = next(generator)
    try:
        workspace = local_agent_service.resolve_local_workspace(db)
        if workspace is None:
            print("No local Questboard profile found. Open the app and add one first.")
            return 1
        if args.action == "grant":
            entry = resume_consent.grant(workspace.id, ttl_hours=args.ttl_hours)
            print(f"Granted resume access for '{workspace.id}'. expires_at={entry['expires_at']}")
        elif args.action == "revoke":
            resume_consent.revoke(workspace.id)
            print(f"Revoked resume access for '{workspace.id}'.")
        else:
            print(resume_consent.status(workspace.id))
        return 0
    finally:
        generator.close()


if __name__ == "__main__":
    raise SystemExit(main())
