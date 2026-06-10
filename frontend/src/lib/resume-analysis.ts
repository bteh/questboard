import type {
  ResumeAnalysisStatus,
  ResumeAnalysisSummary,
  ResumeEducationEntry,
  ResumeParseCode,
  ResumeUploadResponse,
} from '@/types/resume';
import type { WorkspaceResumeUploadResponse } from '@/types/workspace';

/**
 * Upload outcome normalized across the two resume upload routes:
 *
 * - `/resume/{profile}/upload` (legacy/local) returns the full contract:
 *   `parse_status`, `parse_code`, `analysis_status`, `analysis` summary.
 * - `/onboarding/resume` (workspace — the route the UI currently uses)
 *   returns only `resume.parse_status` + `parse_warning` and the raw
 *   analyzer dict (or null). Status fields are derived here.
 */
export interface NormalizedResumeUpload {
  analysisStatus: ResumeAnalysisStatus;
  parseCode: ResumeParseCode;
  analysis: ResumeAnalysisSummary | null;
  parseWarning: string;
  message: string;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function educationList(value: unknown): ResumeEducationEntry[] {
  if (!Array.isArray(value)) return [];
  const entries: ResumeEducationEntry[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const degree = typeof record.degree === 'string' ? record.degree.trim() : '';
    const field = typeof record.field === 'string' ? record.field.trim() : '';
    const institution = typeof record.institution === 'string' ? record.institution.trim() : '';
    if (degree || field || institution) entries.push({ degree, field, institution });
  }
  return entries;
}

/**
 * Coerce either the legacy `ResumeAnalysisSummary` shape or the raw
 * `analyze_resume` dict (workspace route) into a clean summary. Returns
 * null when nothing useful was extracted.
 */
export function normalizeAnalysisSummary(raw: unknown): ResumeAnalysisSummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const record = raw as Record<string, unknown>;
  const summary: ResumeAnalysisSummary = {
    skills: stringList(record.skills),
    suggested_target_roles: stringList(record.suggested_target_roles),
    suggested_keywords: stringList(record.suggested_keywords),
    current_title: typeof record.current_title === 'string' ? record.current_title.trim() : '',
    seniority: typeof record.seniority === 'string' ? record.seniority.trim() : '',
    certifications: stringList(record.certifications),
    education: educationList(record.education),
  };
  const hasContent =
    summary.skills.length > 0 ||
    summary.suggested_target_roles.length > 0 ||
    summary.suggested_keywords.length > 0 ||
    summary.certifications.length > 0 ||
    summary.education.length > 0 ||
    summary.current_title.length > 0;
  return hasContent ? summary : null;
}

/**
 * Detect the scanned/image-based PDF parser warning. The workspace route
 * has no structured `parse_code`, so we match the parser's warning text
 * ("PDF was read but no text was extracted. The PDF might be image-based.").
 */
export function isScannedPdfWarning(warning: string | null | undefined): boolean {
  if (!warning) return false;
  return /image[- ]based|no text (was|could be) extracted|appears to be\s+scanned/i.test(warning);
}

/** Normalize the legacy `/resume/{profile}/upload` response. */
export function normalizeLegacyUpload(response: ResumeUploadResponse): NormalizedResumeUpload {
  return {
    analysisStatus: response.analysis_status,
    parseCode: response.parse_code ?? null,
    analysis: normalizeAnalysisSummary(response.analysis),
    parseWarning: response.parse_status === 'error' ? response.message : '',
    message: response.message,
  };
}

/**
 * Normalize the workspace `/onboarding/resume` response, deriving the
 * status fields the route does not report:
 * - analysis present        -> 'completed'
 * - parse error / scanned   -> 'failed' (analysis cannot run without text)
 * - parse ok, no LLM        -> 'skipped_no_llm'
 * - parse ok, LLM available -> 'failed' (the LLM call returned nothing)
 */
export function normalizeWorkspaceUpload(
  response: WorkspaceResumeUploadResponse,
  options: { llmAvailable: boolean },
): NormalizedResumeUpload {
  const analysis = normalizeAnalysisSummary(response.analysis);
  const parseWarning = response.resume.parse_warning || '';
  const scanned = isScannedPdfWarning(parseWarning);
  const parseFailed = response.resume.parse_status === 'error' || scanned;

  let analysisStatus: ResumeAnalysisStatus;
  if (analysis) {
    analysisStatus = 'completed';
  } else if (parseFailed) {
    analysisStatus = 'failed';
  } else {
    analysisStatus = options.llmAvailable ? 'failed' : 'skipped_no_llm';
  }

  return {
    analysisStatus,
    parseCode: scanned ? 'SCANNED_PDF' : null,
    analysis,
    parseWarning,
    message: response.message,
  };
}

/** Case-insensitive merge keeping first-seen order and original casing. */
export function mergeKeywordLists(...lists: string[][]): string[] {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const list of lists) {
    for (const item of list) {
      const trimmed = item.trim();
      if (!trimmed) continue;
      const key = trimmed.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(trimmed);
    }
  }
  return merged;
}
