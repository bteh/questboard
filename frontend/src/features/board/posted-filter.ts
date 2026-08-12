/* The date filter both lanes share, pinned by posted-filter.test.ts. One
   value is Questboard's local-calendar first-seen window (?days=found-1);
   the others are rolling, source-stated post windows (?days=3|7|30).
   Absent means no additional date filter. */

/* 'found-1' is our own first-seen clock, bounded by local midnight. The
   source date only gets a veto when it verifiably proves the row stale. */
export const POSTED_DAYS = ['3', '7', '30', 'found-1'] as const;
export type PostedDaysKey = (typeof POSTED_DAYS)[number];

/** ?days= however the router round-trips it: '7', 7, or junk. */
export function normalizePostedDays(value: unknown): PostedDaysKey | undefined {
  const text =
    typeof value === 'number' ? String(value) : typeof value === 'string' ? value : '';
  return (POSTED_DAYS as readonly string[]).includes(text)
    ? (text as PostedDaysKey)
    : undefined;
}

/** The select's five options, any time first; '' means no filter. */
export const POSTED_OPTIONS: ReadonlyArray<{ value: '' | PostedDaysKey; label: string }> = [
  { value: '', label: 'any time' },
  { value: 'found-1', label: 'new today' },
  { value: '3', label: 'posted last 3 days' },
  { value: '7', label: 'posted last 7 days' },
  { value: '30', label: 'posted last 30 days' },
];

const CHIP_WORDS: Record<PostedDaysKey, string> = {
  'found-1': 'new today',
  '3': 'posted in the last 3 days',
  '7': 'posted in the last 7 days',
  '30': 'posted in the last 30 days',
};

/** The removable chip's words ("posted this week"). */
export function postedChipLabel(days: PostedDaysKey): string {
  return CHIP_WORDS[days];
}

/** The API's posted_within_days number, from the URL value. */
export function postedWithinDays(days: PostedDaysKey | undefined): number | undefined {
  if (!days || days.startsWith('found-')) return undefined;
  return Number(days);
}

/** The API's found_within_days number; only the found-* values map here. */
export function foundWithinDays(days: PostedDaysKey | undefined): number | undefined {
  if (!days || !days.startsWith('found-')) return undefined;
  return Number(days.slice('found-'.length));
}

/* The one honest clause: the window drops rows whose post date cannot be
   verified, and the reader deserves to know. Speaks only while the filter
   is on AND the shown count actually dropped against the baseline; silent
   while either count is still loading. */
export function hiddenDatesClause({
  days,
  shown,
  baseline,
}: {
  days: PostedDaysKey | undefined;
  shown: number | undefined;
  baseline: number | undefined;
}): string | null {
  if (!days) return null;
  if (days.startsWith('found-')) return null;
  if (shown === undefined || baseline === undefined) return null;
  return shown < baseline ? 'postings without a verifiable date are hidden' : null;
}
