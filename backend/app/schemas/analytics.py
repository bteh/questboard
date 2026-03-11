from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_jobs: int = 0
    avg_score: float | None = None
    strong_apply_count: int = 0
    apply_count: int = 0
    maybe_count: int = 0
    skip_count: int = 0
    applied_count: int = 0
    interviewing_count: int = 0
    offer_count: int = 0
    response_rate: float = 0.0


class ChartDataPoint(BaseModel):
    label: str
    value: float | int
    color: str | None = None
