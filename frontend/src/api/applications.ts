import { apiGet, apiGetBlob, apiPost, apiPatch, apiDelete } from '@/lib/api-client';
import type { ApplicationListResponse, ProfileWorkListResponse, ApplicationResponse, ApplicationCreate, ApplicationUpdate, StatusUpdate, ApplicationFilters } from '@/types/application';

export function getApplications(filters: ApplicationFilters = {}): Promise<ApplicationListResponse> {
  const params: Record<string, string | number | boolean | undefined> = { ...filters };
  // Backend uses sort_dir not sort_order
  if (filters.sort_order) {
    params.sort_dir = filters.sort_order;
    delete params.sort_order;
  }
  return apiGet<ApplicationListResponse>('/applications', params);
}

/** Profile-role retrieval for the local Work lane; the connected agent owns fit. */
export function getProfileWork(filters: ApplicationFilters = {}): Promise<ProfileWorkListResponse> {
  return apiGet<ProfileWorkListResponse>('/applications/profile-work', {
    search: filters.search,
    location: filters.location,
    location_strict: filters.location_strict,
    salary_min: filters.salary_min,
    is_remote: filters.is_remote,
    posted_within_days: filters.posted_within_days,
    page: filters.page,
    page_size: filters.page_size,
  });
}

export function getApplication(id: number): Promise<ApplicationResponse> {
  return apiGet<ApplicationResponse>(`/applications/${id}`);
}

export function createApplication(data: ApplicationCreate): Promise<ApplicationResponse> {
  return apiPost<ApplicationResponse>('/applications', data);
}

export function updateApplication(id: number, data: ApplicationUpdate): Promise<ApplicationResponse> {
  return apiPatch<ApplicationResponse>(`/applications/${id}`, data);
}

export function updateApplicationStatus(id: number, data: StatusUpdate): Promise<ApplicationResponse> {
  return apiPatch<ApplicationResponse>(`/applications/${id}/status`, data);
}

export interface FeedbackUpdate {
  feedback: 'up' | 'down' | '';
  notes?: string | null;
}

export function updateApplicationFeedback(id: number, data: FeedbackUpdate): Promise<ApplicationResponse> {
  return apiPatch<ApplicationResponse>(`/applications/${id}/feedback`, data);
}

export function deleteApplication(id: number): Promise<void> {
  return apiDelete(`/applications/${id}`);
}

export function deduplicateApplications(profile?: string): Promise<{ removed: number; message: string }> {
  const query = profile ? `?profile=${encodeURIComponent(profile)}` : '';
  return apiPost<{ removed: number; message: string }>(`/applications/deduplicate${query}`);
}

/** The ledger's CSV export: the whole career table as a file. */
export function exportApplicationsCsv(profile?: string): Promise<Blob> {
  const query = profile ? `?profile=${encodeURIComponent(profile)}` : '';
  return apiGetBlob(`/applications/export/csv${query}`);
}

export function checkUrls(ids?: number[], limit?: number): Promise<{ checked: number; alive: number; dead: number }> {
  return apiPost<{ checked: number; alive: number; dead: number }>('/applications/check-urls', { ids, limit });
}

export function purgeAllApplications(profile?: string): Promise<{ purged: number; message: string }> {
  const query = profile ? `?profile=${encodeURIComponent(profile)}&confirm=true` : '?confirm=true';
  return apiPost<{ purged: number; message: string }>(`/applications/purge-all${query}`);
}
