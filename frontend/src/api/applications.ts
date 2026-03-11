import { apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api-client';
import type { ApplicationListResponse, ApplicationResponse, ApplicationCreate, ApplicationUpdate, StatusUpdate, ApplicationFilters } from '@/types/application';

export function getApplications(filters: ApplicationFilters = {}): Promise<ApplicationListResponse> {
  const params: Record<string, string | number | boolean | undefined> = { ...filters };
  // Backend uses sort_dir not sort_order
  if (filters.sort_order) {
    params.sort_dir = filters.sort_order;
    delete params.sort_order;
  }
  return apiGet<ApplicationListResponse>('/applications', params);
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

export function deleteApplication(id: number): Promise<void> {
  return apiDelete(`/applications/${id}`);
}

export function deduplicateApplications(profile?: string): Promise<{ removed: number; message: string }> {
  const query = profile ? `?profile=${encodeURIComponent(profile)}` : '';
  return apiPost<{ removed: number; message: string }>(`/applications/deduplicate${query}`);
}

export function checkUrls(ids?: number[], limit?: number): Promise<{ checked: number; alive: number; dead: number }> {
  return apiPost<{ checked: number; alive: number; dead: number }>('/applications/check-urls', { ids, limit });
}
