import { annualBounds } from '@/utils/board-card';
import type { ApplicationResponse } from '@/types/application';

/* The masthead's picks. Everything here is deterministic and provable from
   the rows the API returned: no invented numbers, no coin flips. */

function statedPayMidpoint(app: ApplicationResponse): number | null {
  const { lo, hi } = annualBounds(app);
  if (lo === null && hi === null) return null;
  if (lo !== null && hi !== null) return (lo + hi) / 2;
  return hi ?? lo;
}

function foundAt(app: ApplicationResponse): number {
  const t = app.date_found ? Date.parse(app.date_found) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

/* Highest stated pay wins; a tie goes to the newer find, then the higher id,
   so the same rows always produce the same bounty in any order. */
function outbids(challenger: ApplicationResponse, champion: ApplicationResponse): boolean {
  const a = statedPayMidpoint(challenger) ?? -1;
  const b = statedPayMidpoint(champion) ?? -1;
  if (a !== b) return a > b;
  const fa = foundAt(challenger);
  const fb = foundAt(champion);
  if (fa !== fb) return fa > fb;
  return challenger.id > champion.id;
}

export interface BountyPick {
  app: ApplicationResponse;
  /* true when nothing recent qualified and the section must say so plainly */
  fallback: boolean;
}

/**
 * Today's bounty: the highest-stated-pay row posted in the last three days
 * (recentItems comes from a posted_within_days=3 query, so every row in it
 * has a provable post date). Honest fallback: when no recent row states pay,
 * the newest stated-pay row on the board is shown under a label that says
 * exactly that. Null when the board has no stated pay at all.
 */
export function pickBounty(
  recentItems: ApplicationResponse[],
  newestItems: ApplicationResponse[],
): BountyPick | null {
  let best: ApplicationResponse | null = null;
  for (const app of recentItems) {
    if (statedPayMidpoint(app) === null) continue;
    if (best === null || outbids(app, best)) best = app;
  }
  if (best) return { app: best, fallback: false };

  let newest: ApplicationResponse | null = null;
  for (const app of newestItems) {
    if (statedPayMidpoint(app) === null) continue;
    if (newest === null || foundAt(app) > foundAt(newest) || (foundAt(app) === foundAt(newest) && app.id > newest.id)) {
      newest = app;
    }
  }
  return newest ? { app: newest, fallback: true } : null;
}

export interface LogTile {
  label: string;
  count: number;
}

/**
 * The log strip's tiles, from real statuses only. A zero tile is dropped
 * rather than shown as an empty zero: quiet, not nagging. Counts that have
 * not loaded yet are treated as absent.
 */
export function logStripTiles(counts: {
  applied?: number;
  interviewing?: number;
  offers?: number;
}): LogTile[] {
  const tiles: LogTile[] = [];
  if (counts.applied) tiles.push({ label: 'Applications out', count: counts.applied });
  if (counts.interviewing) tiles.push({ label: 'Interviewing', count: counts.interviewing });
  if (counts.offers) tiles.push({ label: 'Offers', count: counts.offers });
  return tiles;
}
