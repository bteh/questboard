/**
 * Trust & freshness signals for a job card (ghost-job defense).
 *
 * Mirrors the backend `job_finder.job_trust` classifier, but runs at display
 * time so the age is always current. The one rule that matters: a posting with
 * no verifiable date is never "fresh" — that's the false-freshness a repost
 * exploits — so it degrades to `unknown` and we simply say nothing.
 */

export type Freshness = 'fresh' | 'recent' | 'aging' | 'stale' | 'unknown';

const FRESH_MAX_DAYS = 7;
const RECENT_MAX_DAYS = 30;
const AGING_MAX_DAYS = 60;

/** Whole days since the true post date, or null when unknown/unparseable. */
export function postingAgeDays(datePosted?: string | null): number | null {
  if (!datePosted) return null;
  const t = Date.parse(datePosted);
  if (Number.isNaN(t)) return null;
  const days = Math.floor((Date.now() - t) / 86_400_000);
  return Math.max(0, days);
}

export function classifyFreshness(
  datePosted?: string | null,
  dateConfidence?: string | null,
): Freshness {
  if ((dateConfidence || '').toLowerCase() === 'missing') return 'unknown';
  const age = postingAgeDays(datePosted);
  if (age === null) return 'unknown';
  if (age <= FRESH_MAX_DAYS) return 'fresh';
  if (age <= RECENT_MAX_DAYS) return 'recent';
  if (age <= AGING_MAX_DAYS) return 'aging';
  return 'stale';
}

/** Human "Posted 3 days ago" style label, or null when the date is unknown. */
export function postedAgoLabel(
  datePosted?: string | null,
  dateConfidence?: string | null,
): string | null {
  if ((dateConfidence || '').toLowerCase() === 'missing') return null;
  const age = postingAgeDays(datePosted);
  if (age === null) return null;
  if (age === 0) return 'Posted today';
  if (age === 1) return 'Posted yesterday';
  if (age <= 45) return `Posted ${age} days ago`;
  const months = Math.round(age / 30);
  return `Posted ${months} month${months === 1 ? '' : 's'} ago`;
}

/**
 * Short warning to show when a posting is old enough to likely be filled.
 * Returns null for fresh/recent/unknown — we only warn when we can prove age.
 */
export function staleWarning(
  datePosted?: string | null,
  dateConfidence?: string | null,
): string | null {
  const f = classifyFreshness(datePosted, dateConfidence);
  const age = postingAgeDays(datePosted);
  if (f === 'stale') return `Open ${age}+ days, may be filled`;
  if (f === 'aging') return `Open ${age} days`;
  return null;
}

export function isFresh(datePosted?: string | null, dateConfidence?: string | null): boolean {
  return classifyFreshness(datePosted, dateConfidence) === 'fresh';
}
