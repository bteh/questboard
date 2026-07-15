import { describe, expect, it } from 'vitest';
import {
  advanceWorkCutoff,
  countNewSince,
  isNewSince,
  newSinceLine,
  readWorkCutoff,
  splitBySince,
  WORK_SEEN_KEY,
} from './new-since';

function fakeStore(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
  };
}

const LAST_VISIT = '2026-07-13T10:00:00.000Z';

describe('cutoff freeze semantics', () => {
  it('the cutoff read at load stays frozen while the stored value advances', () => {
    const store = fakeStore({ [WORK_SEEN_KEY]: LAST_VISIT });
    const frozen = readWorkCutoff(store);
    expect(frozen).toBe(LAST_VISIT);

    advanceWorkCutoff(new Date('2026-07-14T09:00:00Z'), store);

    /* stored value moved for the NEXT visit */
    expect(readWorkCutoff(store)).toBe('2026-07-14T09:00:00.000Z');
    /* but this visit keeps judging against the frozen cutoff */
    expect(isNewSince('2026-07-13 18:00:00', frozen)).toBe(true);
  });

  it('first ever visit has no cutoff, so nothing claims to be new', () => {
    const store = fakeStore();
    expect(readWorkCutoff(store)).toBeNull();
    expect(isNewSince('2026-07-13 18:00:00', null)).toBe(false);
  });

  it('a garbage stored value reads as no cutoff', () => {
    const store = fakeStore({ [WORK_SEEN_KEY]: 'not a date' });
    expect(readWorkCutoff(store)).toBeNull();
  });
});

describe('isNewSince', () => {
  it('is strictly after: the cutoff instant itself is not new', () => {
    expect(isNewSince('2026-07-13 10:00:00', LAST_VISIT)).toBe(false);
    expect(isNewSince('2026-07-13 10:00:01', LAST_VISIT)).toBe(true);
  });

  it('treats naive date_found as UTC, never local time', () => {
    /* 09:59 naive UTC is before a 10:00Z cutoff no matter the reader zone */
    expect(isNewSince('2026-07-13 09:59:00', LAST_VISIT)).toBe(false);
  });

  it('a re-scraped old row keeps its original date_found and is never new', () => {
    /* the pipeline sets date_found once; a rediscovery only touches
       search_run_id, so the row still compares as old */
    const rescraped = { date_found: '2026-07-01 08:00:00', search_run_id: 'fresh-run' };
    expect(isNewSince(rescraped.date_found, LAST_VISIT)).toBe(false);
  });

  it('missing or unparseable date_found is never new', () => {
    expect(isNewSince(null, LAST_VISIT)).toBe(false);
    expect(isNewSince('garbage', LAST_VISIT)).toBe(false);
  });
});

describe('splitBySince divider grouping', () => {
  const rows = [
    { id: 1, date_found: '2026-07-14 08:00:00' },
    { id: 2, date_found: '2026-07-13 12:00:00' },
    { id: 3, date_found: '2026-07-10 12:00:00' },
    { id: 4, date_found: null },
  ];

  it('groups rows around the cutoff, keeping order inside each group', () => {
    const { fresh, earlier } = splitBySince(rows, LAST_VISIT);
    expect(fresh.map((r) => r.id)).toEqual([1, 2]);
    expect(earlier.map((r) => r.id)).toEqual([3, 4]);
  });

  it('with no cutoff everything is earlier', () => {
    const { fresh, earlier } = splitBySince(rows, null);
    expect(fresh).toEqual([]);
    expect(earlier).toHaveLength(4);
  });
});

describe('countNewSince and the summary line', () => {
  const rows = [
    { date_found: '2026-07-14 08:00:00' },
    { date_found: '2026-07-13 12:00:00' },
    { date_found: '2026-07-10 12:00:00' },
  ];

  it('is exact once all rows are loaded', () => {
    expect(countNewSince(rows, LAST_VISIT, { newestFirst: false, hasMore: false }))
      .toEqual({ count: 2, exact: true });
  });

  it('is exact when newest-first and an older row is already in view', () => {
    expect(countNewSince(rows, LAST_VISIT, { newestFirst: true, hasMore: true }))
      .toEqual({ count: 2, exact: true });
  });

  it('caps honestly when more rows might still be new', () => {
    const allNew = rows.slice(0, 2);
    expect(countNewSince(allNew, LAST_VISIT, { newestFirst: true, hasMore: true }))
      .toEqual({ count: 2, exact: false });
    expect(countNewSince(allNew, LAST_VISIT, { newestFirst: false, hasMore: true }))
      .toEqual({ count: 2, exact: false });
  });

  it('writes the line with the visit date and a plus only when capped', () => {
    expect(newSinceLine({ count: 14, exact: true }, LAST_VISIT))
      .toMatch(/^14 found since your last visit, \w{3} \d{1,2}$/);
    expect(newSinceLine({ count: 24, exact: false }, LAST_VISIT))
      .toMatch(/^24\+ found since your last visit, /);
  });

  it('says nothing when nothing is new or there is no cutoff', () => {
    expect(newSinceLine({ count: 0, exact: true }, LAST_VISIT)).toBeNull();
    expect(newSinceLine({ count: 3, exact: true }, null)).toBeNull();
  });
});
