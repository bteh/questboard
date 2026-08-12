import { describe, expect, it } from 'vitest';
import { checkedAgoLabel } from './freshness';

describe('checkedAgoLabel', () => {
  const now = new Date('2026-07-10T12:00:00Z');

  it('treats the naive API timestamp as UTC, never local time', () => {
    expect(checkedAgoLabel('2026-07-10T10:00:00', now)).toBe('sources checked 2h ago');
  });

  it('says minutes under an hour and days past 36 hours', () => {
    expect(checkedAgoLabel('2026-07-10T11:30:00', now)).toBe('sources checked minutes ago');
    expect(checkedAgoLabel('2026-07-07T12:00:00', now)).toBe('sources checked 3 days ago');
  });

  it('can say that only the latest independently scheduled source was checked', () => {
    expect(checkedAgoLabel('2026-07-10T10:00:00', now, 'latest source')).toBe(
      'latest source checked 2h ago',
    );
  });

  it('says nothing before the first run or on garbage', () => {
    expect(checkedAgoLabel(null, now)).toBeNull();
    expect(checkedAgoLabel(undefined, now)).toBeNull();
    expect(checkedAgoLabel('not a date', now)).toBeNull();
  });
});
