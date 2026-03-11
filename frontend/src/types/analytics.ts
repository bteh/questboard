export interface DashboardStats {
  total_jobs: number;
  avg_score: number | null;
  strong_apply_count: number;
  apply_count: number;
  maybe_count: number;
  skip_count: number;
  applied_count: number;
  interviewing_count: number;
  offer_count: number;
  response_rate: number;
}

export interface ChartDataPoint {
  label: string;
  value: number;
  color?: string;
}
