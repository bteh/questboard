/* The board's honest freshness line, from the scrape run log's checked_at
   (never a guess). Timezone-safe: the API sends naive UTC, so the label is
   computed in UTC and rendered as a relative phrase, per the standing rule
   that freshness is user-centered ("is it alive"), never scraper-centered. */

export function checkedAgoLabel(
  checkedAt: string | null | undefined,
  now: Date = new Date(),
): string | null {
  if (!checkedAt) return null;
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(checkedAt) ? checkedAt : `${checkedAt}Z`;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const mins = Math.max(0, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (mins < 60) return 'sources checked minutes ago';
  const hours = Math.round(mins / 60);
  if (hours <= 36) return `sources checked ${hours}h ago`;
  const days = Math.round(hours / 24);
  return `sources checked ${days} day${days === 1 ? '' : 's'} ago`;
}
