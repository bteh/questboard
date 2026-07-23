/* Pure helpers for the /health ops page. The API speaks in log terms
   (zero_rows, exception); the page speaks plain English. Color carries
   urgency only; the words say what happened. */

import type { FunnelStage } from '@/types/search';

export type VerdictTone = 'ok' | 'warn' | 'bad' | 'quiet';

export function verdictMeta(verdict: string): { label: string; tone: VerdictTone } {
  switch (verdict) {
    case 'failing':
      return { label: 'failing', tone: 'bad' };
    case 'zero_rows':
      return { label: 'went dark', tone: 'bad' };
    case 'dropped':
      return { label: 'volume dropped', tone: 'warn' };
    case 'quiet':
      return { label: 'quiet', tone: 'quiet' };
    default:
      return { label: 'ok', tone: 'ok' };
  }
}

export function reasonMeta(reason: string): { label: string; tone: VerdictTone } {
  switch (reason) {
    case 'exception':
      return { label: 'error', tone: 'bad' };
    case 'timeout':
      return { label: 'timed out', tone: 'bad' };
    case 'zero_rows':
      return { label: 'no rows', tone: 'quiet' };
    default:
      return { label: 'ok', tone: 'ok' };
  }
}

/* Naive ISO from the API is UTC, same rule as the board's freshness line. */
export function agoLabel(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return 'never';
  const zoned = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const then = new Date(zoned);
  if (Number.isNaN(then.getTime())) return 'never';
  const mins = Math.max(0, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours <= 36) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

export function durationLabel(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 90) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

export interface RunRowLike {
  source: string;
  finish_reason: string;
}

export function filterRuns<T extends RunRowLike>(runs: T[], source: string, reason: string): T[] {
  return runs.filter(
    (r) => (!source || r.source === source) && (!reason || r.finish_reason === reason),
  );
}

export function sourceOptions<T extends { source: string; display_name: string }>(
  runs: T[],
): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const r of runs) {
    if (!seen.has(r.source)) seen.set(r.source, r.display_name || r.source);
  }
  return [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export interface HealthEntryLike {
  last_rows: number;
  last_run_at: string | null;
}

/* Tile numbers. rowsLatest sums each source's latest run only, so it reads
   "what the last sweep found", never a 14-day total. lastChecked compares
   ISO strings, safe because the API emits one format. */
export function healthTiles(entries: HealthEntryLike[], needsAttention: number) {
  const rowsLatest = entries.reduce((sum, e) => sum + (e.last_rows || 0), 0);
  const lastChecked = entries.reduce<string | null>((max, e) => {
    if (!e.last_run_at) return max;
    return !max || e.last_run_at > max ? e.last_run_at : max;
  }, null);
  return { sources: entries.length, needsAttention, rowsLatest, lastChecked };
}

/* The last pull's headline: rows found raw, and how many survived every
   filter. Reads the first stage's input and the last stage's output, so it
   holds however many stages ran. Null when no stage was recorded. */
export function lastPullSummary(
  stages: Pick<FunnelStage, 'count_in' | 'count_out'>[],
): { raw: number; kept: number; dropped: number } | null {
  if (stages.length === 0) return null;
  const raw = stages[0].count_in;
  const kept = stages[stages.length - 1].count_out;
  return { raw, kept, dropped: Math.max(raw - kept, 0) };
}
