import { apiGet, apiPost } from '@/lib/api-client';
import type { SearchRequest, RunStatus } from '@/types/search';

export function startSearchRun(data: SearchRequest): Promise<RunStatus> {
  return apiPost<RunStatus>('/search/run', data);
}

export function getRunStatus(runId: string): Promise<RunStatus> {
  return apiGet<RunStatus>(`/search/runs/${runId}/status`);
}

export function getSearchDefaults(profile: string = 'default'): Promise<{
  roles: string[];
  locations: string[];
  keywords: string[];
  max_days_old: number;
  profile: string;
}> {
  return apiGet('/search/defaults', { profile });
}

export interface SearchSuggestions {
  roles: string[];
  keywords: string[];
  locations: string[];
  summary: string;
}

export function suggestSearchParams(profile: string = 'default'): Promise<SearchSuggestions> {
  return apiPost<SearchSuggestions>(`/search/suggest?profile=${encodeURIComponent(profile)}`);
}
