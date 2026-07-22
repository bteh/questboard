/* The demoted filter row must say what it does. The placeholder carries the
   loaded count, and the line under the filters compares what shows against
   the whole lane in plain words. The old copy ("Search these jobs",
   "profile candidates") stays gone. */

import { describe, expect, it } from 'vitest';
import { filterPlaceholder, filterStatusText, pullNote } from './work-toolbar';

describe('the filter box placeholder', () => {
  it('carries the loaded total', () => {
    expect(filterPlaceholder(66)).toBe('Filter these 66 jobs');
  });

  it('falls back to plain words while loading', () => {
    expect(filterPlaceholder(undefined)).toBe('Filter these jobs');
  });

  it('skips the count when it cannot read as a group', () => {
    expect(filterPlaceholder(0)).toBe('Filter these jobs');
    expect(filterPlaceholder(1)).toBe('Filter these jobs');
  });
});

describe('the status line under the filters', () => {
  it('states the bare total when nothing narrows', () => {
    expect(
      filterStatusText({
        shown: 66,
        laneTotal: 66,
        filtered: false,
        checkedAgo: 'sources checked 1h ago',
      }),
    ).toBe('66 jobs · sources checked 1h ago');
  });

  it('compares showing against the lane while a filter narrows', () => {
    expect(
      filterStatusText({
        shown: 12,
        laneTotal: 66,
        filtered: true,
        checkedAgo: 'sources checked 1h ago',
      }),
    ).toBe('Showing 12 of 66 jobs · sources checked 1h ago');
  });

  it('drops the comparison while the lane total is still loading', () => {
    expect(
      filterStatusText({ shown: 12, laneTotal: undefined, filtered: true, checkedAgo: null }),
    ).toBe('Showing 12 jobs');
  });

  it('never claims a lane smaller than what shows', () => {
    expect(
      filterStatusText({ shown: 120, laneTotal: 66, filtered: true, checkedAgo: null }),
    ).toBe('Showing 120 jobs');
  });

  it('holds to freshness alone before the first page lands', () => {
    expect(
      filterStatusText({
        shown: undefined,
        laneTotal: undefined,
        filtered: false,
        checkedAgo: 'sources checked 1h ago',
      }),
    ).toBe('sources checked 1h ago');
    expect(
      filterStatusText({ shown: undefined, laneTotal: undefined, filtered: false, checkedAgo: null }),
    ).toBe('');
  });

  it('speaks singular for one job', () => {
    expect(filterStatusText({ shown: 1, laneTotal: 1, filtered: false, checkedAgo: null })).toBe(
      '1 job',
    );
    expect(filterStatusText({ shown: 1, laneTotal: 66, filtered: true, checkedAgo: null })).toBe(
      'Showing 1 of 66 jobs',
    );
  });
});

describe('pullNote', () => {
  it('names the first saved role and counts the rest', () => {
    expect(pullNote(['Data Engineering Manager', 'Staff Data Engineer', 'Lead Data Engineer'])).toEqual({
      text: 'Pulls fresh postings for Data Engineering Manager and 2 more roles.',
      linkLabel: 'Edit roles',
    });
  });

  it('speaks singular for one saved role', () => {
    expect(pullNote(['Staff Data Engineer'])).toEqual({
      text: 'Pulls fresh postings for Staff Data Engineer.',
      linkLabel: 'Edit roles',
    });
  });

  it('asks for roles when none are saved', () => {
    expect(pullNote([])).toEqual({
      text: 'No target roles saved yet.',
      linkLabel: 'Set roles',
    });
    expect(pullNote(undefined)).toEqual({
      text: 'Pulls fresh postings for your target roles.',
      linkLabel: 'Edit roles',
    });
  });
});
