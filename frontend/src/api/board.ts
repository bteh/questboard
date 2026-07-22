import { apiGet } from '@/lib/api-client';
import type { ApplicationFilters } from '@/types/application';

/** The board filters the summary honors, same names and semantics as the
    /applications list, so the rail counts and the list share predicates. */
export type BoardSummaryFilters = Pick<
  ApplicationFilters,
  | 'search'
  | 'location'
  | 'location_strict'
  | 'salary_min'
  | 'salary_max'
  | 'is_remote'
  | 'first_quest_ok'
  | 'posted_within_days'
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
  kinds: KindSummary[];
}

export function getBoardSummary(filters: BoardSummaryFilters = {}): Promise<BoardSummary> {
  return apiGet<BoardSummary>('/board/summary', { ...filters });
}
