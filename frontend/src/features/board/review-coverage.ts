/** Plain coverage copy for the compact Work toolbar caption. */
export function reviewCoverageText(
  reviewed: number | undefined,
  unreviewed: number | undefined,
): string | null {
  if (reviewed === undefined || unreviewed === undefined) return null;
  const total = reviewed + unreviewed;
  if (total === 0) return null;
  return `${reviewed} of ${total} reviewed`;
}

/** Do not call a partially reviewed lane a global best-match ordering. */
export function workSortLabel(
  bestFirst: boolean,
  unreviewed: number | undefined,
): 'best match' | 'reviewed matches first' | 'newly found' {
  if (!bestFirst) return 'newly found';
  return unreviewed === 0 ? 'best match' : 'reviewed matches first';
}
