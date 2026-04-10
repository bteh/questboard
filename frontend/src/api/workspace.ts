import { apiGet, apiPost, apiUpload } from '@/lib/api-client';
import type {
  GeneratedProfile,
  HostedBootstrap,
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

export function getHostedBootstrap(): Promise<HostedBootstrap> {
  return apiGet<HostedBootstrap>('/me');
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

/**
 * Generate an LLM-tailored search profile from the user's resume.
 *
 * Returns a complete GeneratedProfile (archetype, scoring weights,
 * keywords, recommended scrapers + external boards). Throws if no
 * resume is uploaded yet (400) or if the LLM is not configured (503).
 *
 * Cached on the backend per (workspace_id, resume_hash) so calling
 * this repeatedly during one session does not burn LLM credits.
 */
export function generateWorkspaceProfile(): Promise<GeneratedProfile> {
  return apiPost<GeneratedProfile>('/onboarding/generate-profile');
}
