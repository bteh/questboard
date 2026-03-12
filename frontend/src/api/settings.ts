import { apiGet, apiPut, apiPost } from '@/lib/api-client';
import type { LLMStatus, LLMConfig, LLMTestResult, ProviderPreset, ProviderModel, ProfilePreferences, ProfilePreferencesResponse, ProfileSummary } from '@/types/settings';

export function getLLMStatus(): Promise<LLMStatus> {
  return apiGet<LLMStatus>('/settings/llm');
}

export function updateLLMConfig(config: LLMConfig): Promise<LLMStatus> {
  return apiPut<LLMStatus>('/settings/llm', config);
}

export function testLLMConnection(): Promise<LLMTestResult> {
  return apiPost<LLMTestResult>('/settings/llm/test');
}

export function getLLMPresets(includeInternal = false): Promise<ProviderPreset[]> {
  const params = includeInternal ? '?include_internal=true' : '';
  return apiGet<ProviderPreset[]>(`/settings/llm/presets${params}`);
}

export function fetchProviderModels(base_url: string, api_key: string): Promise<ProviderModel[]> {
  return apiPost<ProviderModel[]>('/settings/llm/models', { base_url, api_key });
}

export function getProfiles(): Promise<ProfileSummary[]> {
  return apiGet<ProfileSummary[]>('/profiles');
}

export function getProfilePreferences(profile: string): Promise<ProfilePreferencesResponse> {
  return apiGet<ProfilePreferencesResponse>(`/profiles/${profile}/preferences`);
}

export function updateProfilePreferences(profile: string, prefs: ProfilePreferences): Promise<ProfilePreferencesResponse> {
  return apiPut<ProfilePreferencesResponse>(`/profiles/${profile}/preferences`, prefs);
}

