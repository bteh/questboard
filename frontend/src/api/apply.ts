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

export interface KitRequest {
  /** user-edited cover letter, saved before the kit builds */
  cover_letter?: string;
}

/** The application kit: everything prefilled, YOU send it.
    Questboard never transmits an application. */
export interface KitResponse {
  success: boolean;
  method: string | null;
  message: string;
  /** where the human acts */
  apply_url: string;
  /** the ATS form, prefilled (empty for unmapped ATS types) */
  fields: Record<string, string>;
}

export function prepareApplication(id: number): Promise<PrepareResponse> {
  return apiPost<PrepareResponse>(`/applications/${id}/prepare`);
}

export function getApplicationKit(id: number, data: KitRequest = {}): Promise<KitResponse> {
  return apiPost<KitResponse>(`/applications/${id}/apply`, data);
}
