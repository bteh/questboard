export interface SearchRequest {
  roles: string[];
  locations: string[];
  keywords: string[];
  include_remote: boolean;
  max_days_old: number;
  use_ai: boolean;
  profile: string;
  mode: 'search_only' | 'search_score' | 'full_pipeline';
}

export interface RunStatus {
  run_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  progress_messages: string[];
  jobs_found: number;
  jobs_scored: number;
  error: string | null;
}

export interface RunResult {
  run_id: string;
  status: string;
  jobs_found: number;
  jobs_scored: number;
  strong_matches: number;
  duration_seconds: number;
  error: string | null;
  sources?: Record<string, number>;
}

export interface ProgressUpdate {
  percent: number;
  stage: string;
  stage_label: string;
  elapsed: number;
}
