import { apiGet, apiPost, apiUpload } from '@/lib/api-client';
import type {
  LocationSuggestion,
  OnboardingState,
  WorkspacePreferences,
  WorkspaceResumeUploadResponse,
  WorkspaceSearchRunResponse,
  WorkspaceSession,
} from '@/types/workspace';

export function bootstrapWorkspaceSession(): Promise<WorkspaceSession> {
  return apiPost<WorkspaceSession>('/session/bootstrap');
}

export function getOnboardingState(): Promise<OnboardingState> {
  return apiGet<OnboardingState>('/onboarding/state');
}

export function uploadWorkspaceResume(file: File): Promise<WorkspaceResumeUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload<WorkspaceResumeUploadResponse>('/onboarding/resume', formData);
}

export function saveWorkspacePreferences(preferences: WorkspacePreferences): Promise<WorkspacePreferences> {
  return apiPost<WorkspacePreferences>('/onboarding/preferences', preferences);
}

export function startOnboardingSearch(preferences: WorkspacePreferences): Promise<WorkspaceSearchRunResponse> {
  return apiPost<WorkspaceSearchRunResponse>('/onboarding/search', preferences);
}

export function suggestLocations(query: string, limit = 8): Promise<LocationSuggestion[]> {
  return apiGet<LocationSuggestion[]>('/locations/suggest', { q: query, limit });
}
