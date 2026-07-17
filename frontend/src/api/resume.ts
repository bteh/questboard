import { apiGet, apiPost, apiUpload } from '@/lib/api-client';
import type { AgentConsentStatus, ResumeStatus, ResumeUploadResponse } from '@/types/resume';

export function getResumeStatus(profile: string): Promise<ResumeStatus> {
  return apiGet<ResumeStatus>(`/resume/${profile}`);
}

export function uploadResume(profile: string, file: File): Promise<ResumeUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload<ResumeUploadResponse>(`/resume/${profile}/upload`, formData);
}

/** Whether the connected agent may read the local resume. */
export function getAgentConsent(): Promise<AgentConsentStatus> {
  return apiGet<AgentConsentStatus>('/agent/resume-consent');
}

export function setAgentConsent(grant: boolean): Promise<AgentConsentStatus> {
  return apiPost<AgentConsentStatus>('/agent/resume-consent', { grant });
}
