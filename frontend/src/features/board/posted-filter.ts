/* The posted-within filter both lanes share, pinned by
   posted-filter.test.ts. The vocabulary is four fixed windows
   (?days=1|3|7|30); absent means any time. Server-side the window is
   conservative: rows without a verifiable ISO post date are dropped, never
   guessed in, matching the board's date honesty. The clause below is how
   the UI owns up to that. */

export const POSTED_DAYS = ['1', '3', '7', '30'] as const;
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
  { value: '1', label: 'today' },
  { value: '3', label: 'last 3 days' },
  { value: '7', label: 'this week' },
  { value: '30', label: 'this month' },
];

const CHIP_WORDS: Record<PostedDaysKey, string> = {
  '1': 'posted today',
  '3': 'posted in the last 3 days',
  '7': 'posted this week',
  '30': 'posted this month',
};

/** The removable chip's words ("posted this week"). */
export function postedChipLabel(days: PostedDaysKey): string {
  return CHIP_WORDS[days];
}

/** The API's posted_within_days number, from the URL value. */
export function postedWithinDays(days: PostedDaysKey | undefined): number | undefined {
  return days ? Number(days) : undefined;
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
  if (shown === undefined || baseline === undefined) return null;
  return shown < baseline ? 'postings without a verifiable date are hidden' : null;
}
