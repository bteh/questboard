import { apiGet, apiPost } from '@/lib/api-client';
import type { SearchDefaults, SearchRequest, RunStatus } from '@/types/search';

export function startSearchRun(data: SearchRequest): Promise<RunStatus> {
  return apiPost<RunStatus>('/search/run', data);
}

export function getRunStatus(runId: string): Promise<RunStatus> {
  return apiGet<RunStatus>(`/search/runs/${runId}/status`);
}

export function getSearchRuns(limit = 20): Promise<RunStatus[]> {
  return apiGet<RunStatus[]>('/search/runs', { limit });
}

export function getSearchDefaults(profile: string = 'default'): Promise<SearchDefaults> {
  return apiGet<SearchDefaults>('/search/defaults', { profile });
}

export interface SearchSuggestions {
  roles: string[];
  keywords: string[];
  locations: string[];
  companies: string[];
  summary: string;
  ai_failed: boolean;
}

export function suggestSearchParams(profile: string = 'default'): Promise<SearchSuggestions> {
  return apiPost<SearchSuggestions>(`/search/suggest?profile=${encodeURIComponent(profile)}`);
}
