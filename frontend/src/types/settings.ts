export interface LLMConfig {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
}

export interface LLMStatus {
  configured: boolean;
  available: boolean;
  provider: string;
  model: string;
  label: string;
}

export interface LLMTestResult {
  success: boolean;
  provider: string;
  model: string;
  message: string;
}

export interface ProviderPreset {
  name: string;
  label: string;
  base_url: string;
  model: string;
  needs_api_key: boolean;
  internal: boolean;
}

export interface ProviderModel {
  id: string;
  name: string;
}

export interface ProfilePreferences {
  current_title: string;
  current_level: string[];
  current_tc: number;
  min_base: number;
  target_total_comp: number;
  auto_apply_enabled: boolean;
  auto_apply_dry_run: boolean;

  // Scoring weights
  scoring_technical: number;
  scoring_leadership: number;
  scoring_career_progression: number;
  scoring_platform: number;
  scoring_comp: number;
  scoring_trajectory: number;
  scoring_culture: number;

  // Thresholds
  threshold_strong_apply: number;
  threshold_apply: number;
  threshold_maybe: number;

  // Toggles
  exclude_staffing_agencies: boolean;
  include_equity: boolean;

  // Career
  min_acceptable_tc: number | null;
}

export interface ProfilePreferencesResponse {
  name: string;
  preferences: ProfilePreferences;
}

export interface ProfileSummary {
  name: string;
  display_name: string;
  description: string;
  target_roles_count: number;
  locations: string[];
}