import { apiGet } from '@/lib/api-client';

export interface ScraperSource {
  name: string;
  display_name: string;
  url: string;
  description: string;
  category: string;
  enabled_by_default: boolean;
  /** Board lane this source feeds; the API serves career sources by default. */
  vertical?: string;
}

export function getScraperSources(vertical?: string): Promise<ScraperSource[]> {
  const suffix = vertical ? `?vertical=${encodeURIComponent(vertical)}` : '';
  return apiGet<ScraperSource[]>(`/scrapers/sources${suffix}`);
}

export interface SourceHealthEntry {
  source: string;
  display_name: string;
  vertical: string;
  /** ok | zero_rows | dropped | failing | quiet (worst first from the API) */
  verdict: string;
  last_run_at: string | null;
  last_finish_reason: string;
  last_rows: number;
  median_rows: number;
  runs_seen: number;
  error_sample: string;
}

export interface SourceHealthResponse {
  sources: SourceHealthEntry[];
  needs_attention: number;
}

export interface ScrapeRunEntry {
  source: string;
  display_name: string;
  vertical: string;
  started_at: string | null;
  duration_s: number;
  /** ok | zero_rows | exception | timeout */
  finish_reason: string;
  rows_found: number;
  /** rows the row contract rejected before they could land */
  rows_invalid: number;
  error_sample: string;
}

export interface ScrapeRunsResponse {
  runs: ScrapeRunEntry[];
}

export function getSourceHealth(days: number): Promise<SourceHealthResponse> {
  return apiGet<SourceHealthResponse>('/scrapers/health', { days });
}

export function getScrapeRuns(days: number, limit = 200): Promise<ScrapeRunsResponse> {
  return apiGet<ScrapeRunsResponse>('/scrapers/runs', { days, limit });
}
