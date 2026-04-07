import type { WorkplacePreference } from '@/lib/profile-preferences';
import type { PlaceSelection } from '@/types/workspace';

export interface SearchRequest {
  roles: string[];
  locations: string[];
  preferred_places: PlaceSelection[];
  keywords: string[];
  companies: string[];
  include_remote: boolean;
  workplace_preference: WorkplacePreference;
  max_days_old: number;
  include_linkedin_jobs: boolean;
  use_ai: boolean;
  profile: string;
  mode: 'search_only' | 'search_score' | 'full_pipeline';
}

export interface SearchRunSnapshot {
  profile: string;
  mode: SearchRequest['mode'];
  roles: string[];
  locations: string[];
  keywords: string[];
  companies?: string[];
  include_remote: boolean;
  workplace_preference: WorkplacePreference;
  max_days_old: number;
  include_linkedin_jobs: boolean;
  use_ai: boolean;
  current_title: string;
  current_level: string;
  current_tc: number | null;
  min_base: number | null;
  target_total_comp: number | null;
  min_acceptable_tc: number | null;
  compensation_currency: string;
  compensation_period: 'hourly' | 'monthly' | 'annual';
  include_equity: boolean | null;
  exclude_staffing_agencies: boolean | null;
}

export interface SearchDefaults {
  roles: string[];
  locations: string[];
  preferred_places: PlaceSelection[];
  keywords: string[];
  companies: string[];
  include_remote: boolean;
  workplace_preference: WorkplacePreference;
  max_days_old: number;
  include_linkedin_jobs: boolean;
  profile: string;
  current_title: string;
  current_level: string;
  current_tc: number | null;
  min_base: number | null;
  target_total_comp: number | null;
  min_acceptable_tc: number | null;
  compensation_currency: string;
  compensation_period: 'hourly' | 'monthly' | 'annual';
  exclude_staffing_agencies: boolean;
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
