/* New-since-your-last-visit for the Jobs lane, frontend-only, pinned by
   new-since.test.ts. The cutoff is the reader's own last visit, stored
   locally, FROZEN at page load, and advanced only after the lane's first
   successful render, so "new" labels never shift mid-visit. New means
   date_found strictly after the cutoff; date_found is written once when a
   row first lands, so a re-scraped old row is never new. */

export const WORK_SEEN_KEY = 'questboard:work-seen.v1';

type KVStore = Pick<Storage, 'getItem' | 'setItem'>;

function browserStorage(): KVStore | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/* date_found comes back as naive UTC, same as restock-logic: pin it so the
   comparison never drifts with the reader's timezone */
function parseUtc(value: string | null | undefined): number | null {
  if (!value) return null;
  let v = value.trim().replace(' ', 'T');
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(v)) v = `${v}Z`;
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

export function readWorkCutoff(storage: KVStore | null = browserStorage()): string | null {
  try {
    const raw = storage?.getItem(WORK_SEEN_KEY) ?? null;
    return raw !== null && parseUtc(raw) !== null ? raw : null;
  } catch {
    return null;
  }
}

export function advanceWorkCutoff(
  now: Date = new Date(),
  storage: KVStore | null = browserStorage(),
): void {
  try {
    storage?.setItem(WORK_SEEN_KEY, now.toISOString());
  } catch {
    /* storage refused: the lane just can't mark new rows next visit */
  }
}

/** Strictly after the cutoff. No cutoff (first ever visit) means nothing is
    new: there is no last visit to claim it against. */
export function isNewSince(dateFound: string | null | undefined, cutoff: string | null): boolean {
  if (!cutoff) return false;
  const found = parseUtc(dateFound);
  const seen = parseUtc(cutoff);
  return found !== null && seen !== null && found > seen;
}

interface Found {
  date_found: string | null;
}

/** Partition for the list divider; original order kept inside each group. */
export function splitBySince<T extends Found>(
  items: T[],
  cutoff: string | null,
): { fresh: T[]; earlier: T[] } {
  const fresh: T[] = [];
  const earlier: T[] = [];
  for (const item of items) {
    (isNewSince(item.date_found, cutoff) ? fresh : earlier).push(item);
  }
  return { fresh, earlier };
}

export interface NewSinceCount {
  count: number;
  exact: boolean;
}

/** Count new rows among the LOADED items only. Exact when every row is
    loaded, or when the list is newest-first and an older row is already in
    view (everything past the flip is older still). Otherwise the summary
    says "n+" and claims nothing more. */
export function countNewSince<T extends Found>(
  items: T[],
  cutoff: string | null,
  opts: { newestFirst: boolean; hasMore: boolean },
): NewSinceCount {
  const count = items.reduce((n, i) => n + (isNewSince(i.date_found, cutoff) ? 1 : 0), 0);
  // the flip proof needs a DATED older row in view: the API sorts NULL
  // date_found first under newest-first, so a null row proves nothing
  const flipLoaded =
    opts.newestFirst && items.some((i) => i.date_found && !isNewSince(i.date_found, cutoff));
  return { count, exact: !opts.hasMore || flipLoaded };
}

/** "14 found since your last visit, Jul 13", or an explicit zero.

    Zero used to return null and the board fell silent, which reads exactly
    like a stale cache or a broken signal. "Nothing new" is an answer; only a
    missing cutoff (first ever visit) has nothing to say. */
export function newSinceLine(res: NewSinceCount, cutoff: string | null): string | null {
  if (!cutoff) return null;
  const t = parseUtc(cutoff);
  const date =
    t === null
      ? ''
      : new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  if (res.count === 0) return `Nothing new since your last visit${date ? `, ${date}` : ''}`;
  return `${res.count}${res.exact ? '' : '+'} found since your last visit${date ? `, ${date}` : ''}`;
}

/** Where "new" starts after a completed pull: the later of the current
    cutoff and the pull's start.

    The cutoff otherwise advances only when the board page mounts, and a
    desktop app stays open for days, so "new here" drifted into meaning "new
    this week". Pressing Get new jobs is the moment the reader starts caring
    what changed, so a finished pull re-anchors "new" at its own start. Never
    moves backward: clock skew must not resurrect week-old rows as new. */
export function cutoffAfterPull(cutoff: string | null, pullStartedAt: string): string | null {
  const pullT = parseUtc(pullStartedAt);
  if (pullT === null) return cutoff;
  const cutoffT = parseUtc(cutoff);
  if (cutoffT !== null && cutoffT >= pullT) return cutoff;
  return pullStartedAt;
}
