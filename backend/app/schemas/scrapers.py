from __future__ import annotations

from pydantic import BaseModel


class ScraperSource(BaseModel):
    name: str
    display_name: str
    url: str
    description: str
    category: str
    enabled_by_default: bool
