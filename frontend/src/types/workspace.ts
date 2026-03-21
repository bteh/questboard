export interface WorkspaceSession {
  workspace_id: string;
  expires_at: string;
  hosted_mode: boolean;
  csrf_required: boolean;
  llm_optional: boolean;
}

export interface PlaceSelection {
  label: string;
  kind: 'city' | 'region' | 'country' | 'manual';
  city: string;
  region: string;
  country: string;
  country_code: string;
  lat: number | null;
  lon: number | null;
  provider: string;
  provider_id: string;
}

export interface CompensationPreference {
  currency: string;
  pay_period: 'hourly' | 'monthly' | 'annual';
  current_comp: number | null;
  min_base: number | null;
  target_total_comp: number | null;
  min_acceptable_tc: number | null;
  include_equity: boolean;
}

export interface WorkspacePreferences {
  roles: string[];
  keywords: string[];
  preferred_places: PlaceSelection[];
  workplace_preference: 'remote_friendly' | 'remote_only' | 'location_only';
  max_days_old: number;
  current_title: string;
  current_level: string;
  compensation: CompensationPreference;
  exclude_staffing_agencies: boolean;
}

export interface WorkspaceResumeStatus {
  exists: boolean;
  filename: string;
  file_size: number;
  parse_status: 'missing' | 'parsed' | 'warning' | 'error';
  parse_warning: string;
}

export interface OnboardingState {
  workspace_id: string;
  needs_resume: boolean;
  needs_preferences: boolean;
  ready_to_search: boolean;
  resume_warning: string;
  llm_optional: boolean;
  llm_available: boolean;
  resume: WorkspaceResumeStatus;
  preferences: WorkspacePreferences;
}

export interface WorkspaceResumeUploadResponse {
  message: string;
  resume: WorkspaceResumeStatus;
  analysis: Record<string, unknown> | null;
}

export interface WorkspaceSearchRunResponse {
  run_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
}

export interface LocationSuggestion {
  label: string;
  kind: 'city' | 'region' | 'country' | 'manual';
  subtitle: string;
  city: string;
  region: string;
  country: string;
  country_code: string;
  lat: number | null;
  lon: number | null;
  provider: string;
  provider_id: string;
}
