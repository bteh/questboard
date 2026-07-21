#!/usr/bin/env python3
"""Re-clean stored job descriptions damaged by the pre-2026-07-21 HTML cleaner.

Thin wrapper around job_finder.models.maintenance so the repair can run
without booting the app:

    python scripts/repair_descriptions.py --db data/job_tracker.db
    python scripts/repair_descriptions.py --db data/job_tracker.db --force

The app also runs this automatically once at startup (see
job_finder.models.database._migrate_db). Safe to re-run; a version marker
in the data_repairs table makes later runs no-ops unless --force is given.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_finder.models.maintenance import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
