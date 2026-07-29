export interface RequirementMatch {
  requirement: string;
  strength: 'strong' | 'partial' | 'missing';
  evidence: string;
  mitigation: string;
}

export interface EvaluationReport {
  archetype: string;
  tldr: string;
  requirements: RequirementMatch[];
  top_gaps: string[];
  recommended_framing: string;
  red_flags: string[];
}

export interface BulletTweak {
  /** The original bullet as it currently appears on the candidate's resume. */
  original_bullet: string;
  /** The rewritten version tailored to the target job. */
  tweaked_bullet: string;
  /** Why this change improves the match — shown as helper text. */
  rationale: string;
  /** Keywords from the JD this rewrite now addresses. */
  target_keywords: string[];
}

/**
 * The resume-optimizer LLM call returns this shape. Mirrors
 * src/job_finder/models/schemas.py::ResumeOptimization. Every field is
 * optional because the LLM may skip sections that don't apply.
 */
export interface ResumeOptimization {
  job_title?: string;
  company?: string;
  bullet_tweaks?: BulletTweak[];
  keywords_to_add?: string[];
  sections_to_emphasize?: string[];
  title_suggestion?: string;
  summary_rewrite?: string;
  ats_compatibility_notes?: string[];
}

/** Per-dimension keyword evidence backing a score. */
export interface ScoreEvidenceEntry {
  matched: string[];
  missing_top: string[];
}

/** Keyed by scoring dimension (technical_skills, leadership_signal, ...). */
export type ScoreEvidence = Record<string, ScoreEvidenceEntry>;

export interface MatchReason {
  code: string;
  label: string;
}

export type AgentFitVerdict = 'strong' | 'good' | 'reach' | 'skip';

/** The connected assistant's fit verdict for one work row (set_work_fit). */
export interface AgentFit {
  rank: number | null;
  verdict: AgentFitVerdict;
  why: string;
  caveat: string;
}

/** Fast offline skill-coverage hint (keyword overlap), shown before the agent runs. */
export interface LocalFit {
  band: 'close' | 'partial' | 'weak';
  skill_count: number;
  matched_skills: string[];
}

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
  // Normalized pay fields, absent on records saved before they shipped.
  // The annualized pair backs pay filtering; display always uses the raw
  // stated numbers so we never show a figure the posting did not state.
  salary_currency?: string;
  salary_period?: string;
  salary_min_annualized?: number | null;
  salary_max_annualized?: number | null;
  // Additive provenance fields — absent on records scored before they shipped.
  salary_source?: 'reported' | 'parsed_from_description' | null;
  work_type_confidence?: 'reported' | 'inferred' | null;
  date_confidence?: 'exact' | 'fuzzy' | 'missing' | null;
  // Trust & freshness (ghost-job defense). date_posted is the job's TRUE
  // original post date (raw source string); direct_from_company is true when
  // the listing links straight to the employer's own ATS/board.
  date_posted?: string | null;
  direct_from_company?: boolean;
}

export interface ApplicationResponse extends ApplicationBase {
  id: number;
  // Quest verticals (career|camera|study|lens|party, matching the UI tokens).
  // Optional because records served before the quest schema lack them; absent
  // always means the career shape.
  vertical?: string;
  event_start?: string | null;
  event_end?: string | null;
  is_rolling?: boolean;
  first_quest_ok?: boolean;
  /** Parsed quest_json served by the API; prefer this over quest_json. */
  quest?: Record<string, unknown> | null;
  quest_json?: string;
  overall_score: number | null;
  technical_score: number | null;
  leadership_score: number | null;
  platform_building_score: number | null;
  comp_potential_score: number | null;
  company_trajectory_score: number | null;
  culture_fit_score: number | null;
  career_progression_score: number | null;
  recommendation: string;
  // Which scale scored the row: 'ai' (LLM) or 'keyword' (offline fallback
  // with lenient thresholds). Null/absent means unscored. Keyword rows must
  // never wear the AI-grade recommendation stamp.
  score_source?: 'ai' | 'keyword' | null;
  /** Retrieval provenance; raw fusion scores are intentionally not exposed. */
  rank_source?: 'hybrid' | 'lexical' | null;
  match_bucket?: 'primary' | 'adjacent' | null;
  /** The connected assistant's own fit verdict from the last run, or null. */
  agent_fit?: AgentFit | null;
  /** Fast offline skill-coverage hint, present on the browse board instantly. */
  local_fit?: LocalFit | null;
  match_reasons?: MatchReason[];
  score_reasoning: string;
  key_strengths: string[];
  key_gaps: string[];
  // Per-dimension matched/missing keywords. Null/absent for older records.
  score_evidence?: ScoreEvidence | null;
  funding_stage: string | null;
  total_funding: string | null;
  employee_count: string | null;
  company_type: string;
  company_intel_json: string;
  resume_tweaks_json: string;
  evaluation_report_json: string;
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
  user_feedback: string;
  feedback_notes: string;
  // Run that last surfaced this job (overwritten on every rediscovery).
  search_run_id: string | null;
  // Run that originally found this job — set once, never overwritten. Used
  // by the UI to mark truly-new jobs in the latest run vs re-discoveries.
  first_seen_run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApplicationListResponse {
  items: ApplicationResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProfileWorkListResponse extends ApplicationListResponse {
  profile_configured: boolean;
  resume_available: boolean;
  jurisdiction_configured: boolean;
  candidate_queries: string[];
  filters_applied: Record<string, unknown>;
  ranking_owner: 'connected_agent';
  /** source kind -> count across the full career inventory, for browse chips */
  source_categories?: Record<string, number>;
  retrieval_note: string;
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
  /** The row's lane; the log composer writes 'personal', default career. */
  vertical?: string;
}

export interface ApplicationUpdate {
  status?: string;
  notes?: string;
  contact_name?: string;
  contact_email?: string;
  referral_source?: string;
  /** User-entered quest facts as a JSON object string, e.g. {"paid_out": 45}. */
  quest_json?: string;
}

export interface StatusUpdate {
  status: string;
  notes?: string;
}

export interface ApplicationFilters {
  /** Vertical(s) to list, single or comma list; the API defaults to career. */
  vertical?: string;
  /** Drop rows whose event_start is already past; rows with no event date pass. */
  upcoming_only?: boolean;
  /** true keeps only rows whose source stated a beginner-friendly signal. */
  first_quest_ok?: boolean;
  /** Keep only rows provably posted in the last N days; unverifiable dates drop. */
  posted_within_days?: number;
  found_within_days?: number;
  /** Keep only rows whose taping/session date falls in the next N days. */
  event_within_days?: number;
  status?: string;
  recommendation?: string;
  /** Scoring provenance: 'ai' keeps only LLM-scored rows, 'keyword' only fallback-scored rows. */
  score_source?: 'ai' | 'keyword';
  company_type?: string;
  work_type?: string;
  /** place text; remote/online/nationwide and no-place rows always pass */
  location?: string;
  /** "near me only": with a location set, keep only rows that match it,
      dropping remote/nationwide/placeless. No-op without a location. */
  location_strict?: boolean;
  /** a kind's own sub-filter (facet id from @questboard/kinds); needs the
      kind in vertical, the API 400s otherwise */
  facet?: string;
  source?: string;
  /** Browse by source kind: remote | ats | startup | crypto | community | jobspy */
  source_category?: string;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  min_score?: number;
  is_remote?: boolean;
  /** Annual pay floor; the API keeps rows with no stated pay. */
  salary_min?: number;
  /** Annual pay ceiling; the API keeps rows with no stated pay. */
  salary_max?: number;
  page?: number;
  page_size?: number;
  profile?: string;
  search_run_id?: string;
  first_seen_run_id?: string;
  /**
   * mine = your rows only (the log). board = the felt: hosted mode adds
   * the shared quest pool alongside your rows; identical in local mode.
   */
  scope?: 'mine' | 'board';
}
