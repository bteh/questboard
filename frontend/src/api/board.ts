import { apiGet } from '@/lib/api-client';

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

export function getBoardSummary(): Promise<BoardSummary> {
  return apiGet<BoardSummary>('/board/summary');
}
