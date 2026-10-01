/**
 * Trust & freshness signals for a job card (ghost-job defense).
 *
 * Mirrors the backend `job_finder.job_trust` classifier, but runs at display
 * time so the age is always current. The one rule that matters: a posting with
 * no verifiable date is never "fresh" (that's the false-freshness a repost
 * exploits), so it degrades to `unknown` and we simply say nothing.
 *
 * A row the board kept past the saved window because the source still lists,
 * updated, or verified it (freshness_basis) is never called stale; its posted
 * line reads "older, still open" instead of implying it is new.
 */

import type { FreshnessBasis } from '@/types/application';

export type Freshness = 'fresh' | 'recent' | 'aging' | 'stale' | 'unknown';

const FRESH_MAX_DAYS = 7;
const RECENT_MAX_DAYS = 30;
const AGING_MAX_DAYS = 60;
const DAY_COUNT_MAX_DAYS = 45;

/** Whole days since the true post date, or null when unknown/unparseable. */
export function postingAgeDays(datePosted?: string | null): number | null {
  if (!datePosted) return null;
  const t = Date.parse(datePosted);
  if (Number.isNaN(t)) return null;
  const days = Math.floor((Date.now() - t) / 86_400_000);
  return Math.max(0, days);
}

function knownAgeDays(datePosted?: string | null, dateConfidence?: string | null): number | null {
  if ((dateConfidence || '').toLowerCase() === 'missing') return null;
  return postingAgeDays(datePosted);
}

/** True when the board kept the row on the source's word, not on the post date. */
function keptOpen(basis?: FreshnessBasis | null): boolean {
  return basis === 'updated' || basis === 'listed' || basis === 'verified_open';
}

export function classifyFreshness(
  datePosted?: string | null,
  dateConfidence?: string | null,
  basis?: FreshnessBasis | null,
): Freshness {
  const age = knownAgeDays(datePosted, dateConfidence);
  if (age === null) return 'unknown';
  if (age <= FRESH_MAX_DAYS) return 'fresh';
  if (age <= RECENT_MAX_DAYS || keptOpen(basis)) return 'recent';
  if (age <= AGING_MAX_DAYS) return 'aging';
  return 'stale';
}

/** Human "Posted 3 days ago" style label, or null when the date is unknown. */
export function postedAgoLabel(
  datePosted?: string | null,
  dateConfidence?: string | null,
  basis?: FreshnessBasis | null,
  dateUpdated?: string | null,
): string | null {
  const age = knownAgeDays(datePosted, dateConfidence);
  if (keptOpen(basis) && (age === null || age > DAY_COUNT_MAX_DAYS)) {
    return stillOpenLabel(basis, dateUpdated);
  }
  if (age === null) return null;
  if (age === 0) return 'Posted today';
  if (age === 1) return 'Posted yesterday';
  if (age <= DAY_COUNT_MAX_DAYS) return `Posted ${age} days ago`;
  const months = Math.round(age / 30);
  return `Posted ${months} month${months === 1 ? '' : 's'} ago`;
}

function stillOpenLabel(basis?: FreshnessBasis | null, dateUpdated?: string | null): string {
  const updated = basis === 'updated' ? postingAgeDays(dateUpdated) : null;
  return updated === null ? 'older, still open' : `updated ${updated}d ago, still open`;
}

/**
 * Short warning to show when a posting is old enough to likely be filled.
 * Returns null for fresh/recent/unknown, and for rows the board kept on the
 * source's word; we only warn when we can prove age and nobody vouches for it.
 */
export function staleWarning(
  datePosted?: string | null,
  dateConfidence?: string | null,
  basis?: FreshnessBasis | null,
): string | null {
  const f = classifyFreshness(datePosted, dateConfidence, basis);
  const age = postingAgeDays(datePosted);
  if (f === 'stale') return `Open ${age}+ days, may be filled`;
  if (f === 'aging') return `Open ${age} days`;
  return null;
}

export function isFresh(datePosted?: string | null, dateConfidence?: string | null): boolean {
  return classifyFreshness(datePosted, dateConfidence) === 'fresh';
}
