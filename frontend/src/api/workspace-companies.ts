import { apiGet, apiPost, apiDelete } from '@/lib/api-client';
import type { WatchlistAddPayload, WatchlistResponse } from '@/api/watchlist';

/* The watched-company store the desktop pull actually reads: the workspace's
   target companies (names) plus a resolved ats/slug cache. Adding here always
   drives the next refresh. Same response shape as the legacy profile watchlist,
   so the Companies tab reuses those types. */

export function getWorkspaceCompanies(): Promise<WatchlistResponse> {
  return apiGet<WatchlistResponse>('/workspace/companies');
}

export function addWorkspaceCompany(payload: WatchlistAddPayload): Promise<WatchlistResponse> {
  return apiPost<WatchlistResponse>('/workspace/companies', {
    name: payload.name ?? '',
    url: payload.url ?? '',
  });
}

export function removeWorkspaceCompany(name: string): Promise<WatchlistResponse> {
  return apiDelete<WatchlistResponse>(`/workspace/companies/${encodeURIComponent(name)}`);
}
