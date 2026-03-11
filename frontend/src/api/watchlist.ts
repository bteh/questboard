import { apiGet, apiPost, apiDelete } from '@/lib/api-client';

export interface WatchlistCompany {
  name: string;
  slug: string;
  ats: string;
  job_count: number;
  careers_url: string;
}

export interface WatchlistResponse {
  profile: string;
  companies: WatchlistCompany[];
}

export function getWatchlist(profile: string): Promise<WatchlistResponse> {
  return apiGet<WatchlistResponse>(`/profiles/${profile}/watchlist`);
}

export function addWatchlistCompany(profile: string, name: string): Promise<WatchlistResponse> {
  return apiPost<WatchlistResponse>(`/profiles/${profile}/watchlist`, { name });
}

export function removeWatchlistCompany(profile: string, name: string): Promise<WatchlistResponse> {
  return apiDelete<WatchlistResponse>(`/profiles/${profile}/watchlist/${encodeURIComponent(name)}`);
}
