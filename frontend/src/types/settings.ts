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
}

export interface ProfilePreferencesResponse {
  name: string;
  preferences: ProfilePreferences;
}