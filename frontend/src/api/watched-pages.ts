import { apiDelete, apiGet, apiPost } from '@/lib/api-client';

export interface WatchedPage {
  id: number;
  url: string;
  name: string;
  added_at: string | null;
  last_checked_at: string | null;
  last_found: number;
  last_error: string;
}

export interface WatchedPageSuggestion {
  name: string;
  url: string;
  area: string;
  hosting: string;
  note: string;
}

export interface WatchedPagesResponse {
  pages: WatchedPage[];
  suggestions: WatchedPageSuggestion[];
  message: string;
}

export function getWatchedPages(): Promise<WatchedPagesResponse> {
  return apiGet<WatchedPagesResponse>('/watched-pages');
}

export function addWatchedPage(url: string): Promise<WatchedPagesResponse> {
  return apiPost<WatchedPagesResponse>('/watched-pages', { url });
}

export function removeWatchedPage(id: number): Promise<WatchedPagesResponse> {
  return apiDelete<WatchedPagesResponse>(`/watched-pages/${id}`);
}
