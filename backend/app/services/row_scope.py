"""Row visibility in one place: who sees which application rows.

Local and desktop own ONE pool (workspace_id NULL); reads take no filter.
Hosted mode splits by what the row is:

- career rows are personal (your resume drove the search), scoped
  strictly to your workspace, exactly as before;
- quest rows are THE BOARD, one shared pool the scheduler sweeps
  (workspace_id NULL), the same felt for every visitor;
- touching a shared quest row (clip, status, notes) clones it into your
  workspace first, so your log stays yours and the shared row stays
  pristine for everyone else. Reads then hide the shared original behind
  your copy (dedupe by job_url).
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select

from job_finder.models.database import ApplicationRecord


def visible_rows_filter(workspace_id: str | None):
    """The board-read filter for a hosted workspace; None means no filter.

    Yours (career rows and touched quest copies) plus the shared quest
    pool, minus shared rows you already copied.
    """
    if not workspace_id:
        return None
    my_urls = select(ApplicationRecord.job_url).where(
        ApplicationRecord.workspace_id == workspace_id
    ).scalar_subquery()
    return or_(
        ApplicationRecord.workspace_id == workspace_id,
        and_(
            ApplicationRecord.workspace_id.is_(None),
            ApplicationRecord.vertical != "career",
            ApplicationRecord.job_url.notin_(my_urls),
        ),
    )


def shared_quest_row_filter(app_id: int):
    """A single shared quest row by id: the clone-on-touch lookup."""
    return and_(
        ApplicationRecord.id == app_id,
        ApplicationRecord.workspace_id.is_(None),
        ApplicationRecord.vertical != "career",
    )
