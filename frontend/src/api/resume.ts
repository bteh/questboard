import { apiGet, apiUpload } from '@/lib/api-client';
import type { ResumeStatus, ResumeUploadResponse } from '@/types/resume';

export function getResumeStatus(profile: string): Promise<ResumeStatus> {
  return apiGet<ResumeStatus>(`/resume/${profile}`);
}

export function uploadResume(profile: string, file: File): Promise<ResumeUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload<ResumeUploadResponse>(`/resume/${profile}/upload`, formData);
}
