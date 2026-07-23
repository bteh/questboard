import { apiGet, apiPost, apiDelete } from '@/lib/api-client';

export interface WatchlistCompany {
  name: string;
  slug: string;
  ats: string;
  job_count: number;
  careers_url: string;
}

/* An add carries a name, a careers link, or both. A link resolves to its
   exact board token on the backend; name plus link completes an existing
   unfinished entry in place. */
export interface WatchlistAddPayload {
  name?: string;
  url?: string;
}

export interface WatchlistResponse {
  profile: string;
  companies: WatchlistCompany[];
  /* Set when an add finished without a confirmed board, so the UI can ask
     for the careers link instead of showing the entry as healthy. */
  message?: string;
}

export function getWatchlist(profile: string): Promise<WatchlistResponse> {
  return apiGet<WatchlistResponse>(`/profiles/${profile}/watchlist`);
}

export function addWatchlistCompany(
  profile: string,
  payload: WatchlistAddPayload,
): Promise<WatchlistResponse> {
  return apiPost<WatchlistResponse>(`/profiles/${profile}/watchlist`, {
    name: payload.name ?? '',
    url: payload.url ?? '',
  });
}

export function removeWatchlistCompany(profile: string, name: string): Promise<WatchlistResponse> {
  return apiDelete<WatchlistResponse>(`/profiles/${profile}/watchlist/${encodeURIComponent(name)}`);
}
