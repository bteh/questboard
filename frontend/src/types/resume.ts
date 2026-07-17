export interface ResumeStatus {
  profile: string;
  exists: boolean;
  filename: string;
  file_size: number;
  path: string;
}

export interface AgentConsentStatus {
  granted: boolean;
  granted_at: string | null;
  expires_at: string | null;
}

export type ResumeAnalysisStatus = 'completed' | 'skipped_no_llm' | 'failed' | 'analysis_error' | 'quota_exhausted';

export type ResumeParseCode = 'SCANNED_PDF' | null;

export interface ResumeEducationEntry {
  degree: string;
  field: string;
  institution: string;
}

/** Summary of what resume analysis extracted, echoed in the upload response. */
export interface ResumeAnalysisSummary {
  skills: string[];
  suggested_target_roles: string[];
  suggested_keywords: string[];
  current_title: string;
  seniority: string;
  certifications: string[];
  education: ResumeEducationEntry[];
}

export interface ResumeUploadResponse {
  profile: string;
  filename: string;
  message: string;
  parse_status: 'ok' | 'error';
  parse_code: ResumeParseCode;
  analysis_status: ResumeAnalysisStatus;
  analysis: ResumeAnalysisSummary | null;
}
