"""ApplicationRecord model — re-exported from src for single source of truth.

All schema changes should be made in src/job_finder/models/database.py.
The backend imports from there to avoid duplication and schema drift.
"""

from job_finder.models.database import ApplicationRecord

__all__ = ["ApplicationRecord"]
