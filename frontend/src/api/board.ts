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
  kinds: KindSummary[];
}

export function getBoardSummary(): Promise<BoardSummary> {
  return apiGet<BoardSummary>('/board/summary');
}
