export interface ApplicationBase {
  job_title: string;
  company: string;
  location: string;
  job_url: string;
  source: string;
  description: string;
  is_remote: boolean;
  work_type: string;
  salary_min: number | null;
  salary_max: number | null;
}

export interface ApplicationResponse extends ApplicationBase {
  id: number;
  overall_score: number | null;
  technical_score: number | null;
  leadership_score: number | null;
  platform_building_score: number | null;
  comp_potential_score: number | null;
  company_trajectory_score: number | null;
  culture_fit_score: number | null;
  career_progression_score: number | null;
  recommendation: string;
  score_reasoning: string;
  key_strengths: string[];
  key_gaps: string[];
  funding_stage: string | null;
  total_funding: string | null;
  employee_count: string | null;
  company_type: string;
  company_intel_json: string;
  resume_tweaks_json: string;
  cover_letter: string;
  application_method: string;
  profile: string;
  status: string;
  date_found: string | null;
  date_applied: string | null;
  notes: string;
  contact_name: string;
  contact_email: string;
  referral_source: string;
  url_status: string;
  last_checked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApplicationListResponse {
  items: ApplicationResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApplicationCreate {
  job_title: string;
  company: string;
  location?: string;
  job_url?: string;
  source?: string;
  description?: string;
  is_remote?: boolean;
  salary_min?: number | null;
  salary_max?: number | null;
  status?: string;
  notes?: string;
  profile?: string;
}

export interface ApplicationUpdate {
  status?: string;
  notes?: string;
  contact_name?: string;
  contact_email?: string;
  referral_source?: string;
}

export interface StatusUpdate {
  status: string;
  notes?: string;
}

export interface ApplicationFilters {
  status?: string;
  recommendation?: string;
  company_type?: string;
  work_type?: string;
  source?: string;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  min_score?: number;
  is_remote?: boolean;
  page?: number;
  page_size?: number;
  profile?: string;
  search_run_id?: string;
}
