import { apiPost } from '@/lib/api-client';
import { questRefreshVerticals } from '@/features/board/kind-params';

/* The quest refresh call and its lines, pinned by quest-restock.test.tsx.
   POST /quests/refresh runs the quest scrapers synchronously and answers
   with a summary on the same request; no run id, no pipeline. Career stays
   on its own lane's "Get new jobs" and never rides this call. */

export interface QuestRefreshSummary {
  verticals: string[];
  found: number;
  saved: number;
  deduped: number;
  skipped_stale: number;
  expired: number;
  sources: Record<string, unknown>;
}

export function refreshQuests(): Promise<QuestRefreshSummary> {
  return apiPost<QuestRefreshSummary>('/quests/refresh', {
    verticals: questRefreshVerticals(),
  });
}

/** The after line: counts plainly, never celebrates. */
export function questRestockDoneLine(saved: number): string {
  if (saved === 0) return 'Checked. Nothing new right now.';
  if (saved === 1) return '1 new quest pinned.';
  return `${saved} new quests pinned.`;
}
