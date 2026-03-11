import { apiPost } from '@/lib/api-client';

export interface ApplicantInfo {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
}

export interface PrepareResponse {
  ats_type: string | null;
  ats_detected: boolean;
  cover_letter: string | null;
  resume_tweaks: Record<string, unknown> | null;
  applicant_info: ApplicantInfo;
  job_title: string;
  company: string;
  job_url: string;
}

export interface SubmitRequest {
  cover_letter?: string;
  dry_run?: boolean;
}

export interface SubmitResponse {
  success: boolean;
  method: string | null;
  message: string;
  dry_run: boolean;
}

export function prepareApplication(id: number): Promise<PrepareResponse> {
  return apiPost<PrepareResponse>(`/applications/${id}/prepare`);
}

export function submitApplication(id: number, data: SubmitRequest = {}): Promise<SubmitResponse> {
  return apiPost<SubmitResponse>(`/applications/${id}/apply`, data);
}
