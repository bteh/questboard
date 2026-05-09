import { apiGet, apiPost } from '@/lib/api-client';
import type { FunnelSummary, SearchDefaults, SearchRequest, RunStatus } from '@/types/search';

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

export function getLatestFunnel(): Promise<FunnelSummary> {
  return apiGet<FunnelSummary>('/search/funnel/latest');
}

export function getRunFunnel(runId: string): Promise<FunnelSummary> {
  return apiGet<FunnelSummary>(`/search/runs/${runId}/funnel`);
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
