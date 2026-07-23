/* The board restock line's state logic, pinned by restock-line.test.ts.
   Three states, per the entry-experience spec:
   - a run is live: "Restocking, {n} of {m} sources in."
   - the newest row landed inside the week: "Restocked {relative date}. Restock"
   - nothing landed for 7+ days (or ever): "Nothing new this week."
   The date is the newest row's date_found, which the pipeline stores as
   naive UTC; parsing pins it to UTC so the age never drifts with the
   reader's timezone. */

export const STALE_AFTER_DAYS = 7;

export type RestockLineState =
  | { kind: 'fresh'; label: string }
  | { kind: 'stale' };

/** Whole days since date_found, or null when missing/unparseable. */
export function restockAgeDays(
  newestDateFound: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!newestDateFound) return null;
  let value = newestDateFound.trim().replace(' ', 'T');
  // date_found is stored as naive UTC; make that explicit for the parser.
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) value = `${value}Z`;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const days = Math.floor((now.getTime() - t) / 86_400_000);
  return Math.max(0, days);
}

/** "today", "yesterday", "3 days ago". */
export function restockedWhen(age: number): string {
  if (age === 0) return 'today';
  if (age === 1) return 'yesterday';
  return `${age} days ago`;
}

export function restockLine(
  newestDateFound: string | null | undefined,
  now: Date = new Date(),
): RestockLineState {
  const age = restockAgeDays(newestDateFound, now);
  // An empty board and an unreadable date both read as stale: the line
  // never claims a restock it cannot prove.
  if (age === null || age >= STALE_AFTER_DAYS) return { kind: 'stale' };
  return { kind: 'fresh', label: restockedWhen(age) };
}

export interface RestockProgress {
  done: number;
  total: number;
}

/* The run's own progress messages carry the source arithmetic: the scraper
   registry announces "Searching {m} additional sources in parallel..." and
   then reports each source back with one of three line shapes. Counting
   those lines is what the work toolbar's run status line reads; nothing
   here is invented. */
const TOTAL_RE = /Searching (\d+) additional sources in parallel/;
const SOURCE_DONE_RES = [
  /^\s+Found \d+ jobs from .+/,
  /^\s+.+: no results$/,
  /^\s+.+: timed out$/,
];

export function restockProgress(messages: string[]): RestockProgress | null {
  let total: number | null = null;
  let done = 0;
  for (const msg of messages) {
    const m = TOTAL_RE.exec(msg);
    if (m) {
      // A fresh batch announcement restarts the count.
      total = parseInt(m[1], 10);
      done = 0;
      continue;
    }
    if (total !== null && SOURCE_DONE_RES.some((re) => re.test(msg))) {
      done += 1;
    }
  }
  if (total === null || total === 0) return null;
  return { done: Math.min(done, total), total };
}
