export interface WorkspaceSession {
  workspace_id: string;
  expires_at: string;
  hosted_mode: boolean;
  csrf_required: boolean;
  llm_optional: boolean;
  session_token?: string | null;
  csrf_token?: string | null;
}

export interface HostedUserProfile {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string;
  auth_provider: string;
  email_verified: boolean;
}

export interface HostedWorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  role: string;
  plan: string;
  subscription_status: string;
}

export interface HostedFeatureFlags {
  platform_managed_ai: boolean;
  runtime_llm_configurable: boolean;
  billing_enabled: boolean;
}

export interface DevHostedPersona {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string;
  headline: string;
  background: string;
  job_search_focus: string;
  current_title: string;
  current_level: string;
  target_roles: string[];
  keywords: string[];
  preferred_places: string[];
  workplace_preference: 'remote_friendly' | 'remote_only' | 'location_only';
  resume_filename: string;
}

export interface DevHostedLoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  persona: DevHostedPersona;
}

export interface DevHostedUser {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string;
  auth_provider: string;
  seeded: boolean;
}

export interface DevHostedRegisterResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: DevHostedUser;
}

export interface HostedBootstrap {
  hosted_mode: true;
  auth_required: true;
  csrf_required: false;
  llm_optional: boolean;
  user: HostedUserProfile;
  workspace: HostedWorkspaceSummary;
  features: HostedFeatureFlags;
}

export interface PlaceSelection {
  label: string;
  kind: 'city' | 'region' | 'country' | 'manual';
  match_scope: 'city' | 'metro' | 'region' | 'country';
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
  companies: string[];
  preferred_places: PlaceSelection[];
  workplace_preference: 'remote_friendly' | 'remote_only' | 'location_only';
  max_days_old: number;
  include_linkedin_jobs: boolean;
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
  has_started_search: boolean;
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

/**
 * LLM-tailored search profile generated from the workspace's resume.
 *
 * The whole point of this object is to make Launchboard work for *any*
 * career, not just the seven hardcoded archetype templates. A user with
 * an unusual or multi-domain background gets a profile generated
 * specifically for them — covering niches we never modeled (climate
 * tech, vet med, MTS at frontier labs, biotech regulatory, etc.).
 *
 * Wire-compat with the backend GeneratedProfileResponse and the
 * pipeline-layer GeneratedProfile pydantic model — same field names
 * top to bottom.
 */
export interface GeneratedProfileScoring {
  technical_skills: number;
  leadership_signal: number;
  career_progression: number;
  platform_building: number;
  comp_potential: number;
  company_trajectory: number;
  culture_fit: number;
}

export interface GeneratedProfileKeywords {
  technical: string[];
  leadership: string[];
  signal_terms: string[];
}

export interface GeneratedProfileCompensation {
  currency: string;
  pay_period: string;
  min_base: number;
  target_total_comp: number;
  include_equity: boolean;
}

export interface GeneratedProfile {
  detected_archetype: string;
  confidence: number;
  reasoning: string;
  closest_template: string | null;
  career_target: string;
  seniority_signal: string;
  scoring: GeneratedProfileScoring;
  keywords: GeneratedProfileKeywords;
  target_roles: string[];
  compensation: GeneratedProfileCompensation;
  enabled_scrapers: string[];
  recommended_external_boards: string[];
  primary_strengths: string[];
  development_areas: string[];
  cached: boolean;
}

export interface LocationSuggestion {
  label: string;
  kind: 'city' | 'region' | 'country' | 'manual';
  match_scope: 'city' | 'metro' | 'region' | 'country';
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
