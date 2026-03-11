export interface ScheduleConfig {
  profile: string;
  enabled: boolean;
  interval_hours: number;
  mode: 'search_only' | 'search_score' | 'full_pipeline';
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_jobs_found: number;
  last_run_new_jobs: number;
}

export interface ScheduleUpdate {
  enabled: boolean;
  interval_hours: number;
  mode: string;
}
