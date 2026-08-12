import { apiGet } from '@/lib/api-client';
import type { ApplicationFilters } from '@/types/application';
import type { SourceCoverage } from '@/types/search';

/** The board filters the summary honors, same names and semantics as the
    /applications list, so the rail counts and the list share predicates. */
export type BoardSummaryFilters = Pick<
  ApplicationFilters,
  | 'search'
  | 'location'
  | 'location_strict'
  | 'salary_min'
  | 'salary_max'
  | 'salary_currency'
  | 'is_remote'
  | 'first_quest_ok'
  | 'posted_within_days'
  | 'found_within_days'
  | 'timezone_name'
>;

export interface KindSummary {
  id: string;
  label: string;
  sub: string;
  hue: string;
  order: number;
  count: number;
  new_today: number;
}

export interface BoardSummary {
  total: number;
  new_today: number;
  /** last healthy quest-source run (ISO, naive UTC); null before the first */
  checked_at: string | null;
  /** last fully completed Find Work pull; partial source responses do not count */
  career_checked_at: string | null;
  /** last healthy Side Quest source run */
  side_quest_checked_at: string | null;
  career_refresh: CareerRefreshReceipt | null;
  kinds: KindSummary[];
}

export interface CareerRefreshReceipt {
  run_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  jobs_found: number;
  new_jobs: number;
  error: string | null;
  source_coverage: SourceCoverage | null;
}

export function getBoardSummary(filters: BoardSummaryFilters = {}): Promise<BoardSummary> {
  return apiGet<BoardSummary>('/board/summary', { ...filters });
}
