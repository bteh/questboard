/* The demoted filter row must say what it does. The placeholder carries the
   loaded count, and the line under the filters compares what shows against
   the whole lane in plain words. The old copy ("Search these jobs",
   "profile candidates") stays gone. */

import { describe, expect, it } from 'vitest';
import {
  filterPlaceholder,
  filterTrayCaption,
  filterStatusText,
  primaryRunKind,
  pullReceipt,
} from './work-toolbar-logic';
import { reviewCoverageText, workSortLabel } from './review-coverage';

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

describe('the filter tray contract', () => {
  it('says filters apply automatically and separates them from the source pull', () => {
    expect(filterTrayCaption(false)).toBe(
      'Filters update this board automatically · Get new jobs checks sources and reranks using your saved search',
    );
  });

  it('announces the in-place query while a changed filter is loading', () => {
    expect(filterTrayCaption(true)).toBe(
      'Applying filters… · Get new jobs checks sources and reranks using your saved search',
    );
  });
});

describe('assistant review coverage', () => {
  it('states current coverage without pretending stale fits still count', () => {
    expect(reviewCoverageText(51, 152)).toBe('51 of 203 reviewed');
  });

  it('stays quiet while loading or on an empty lane', () => {
    expect(reviewCoverageText(undefined, undefined)).toBeNull();
    expect(reviewCoverageText(0, 0)).toBeNull();
  });

  it('does not claim a global best match while jobs remain unreviewed', () => {
    expect(workSortLabel(true, 152)).toBe('reviewed matches first');
    expect(workSortLabel(true, 0)).toBe('best match');
    expect(workSortLabel(false, 152)).toBe('newly found');
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

  it('appends the honest hidden-dates clause while the days filter narrows', () => {
    expect(
      filterStatusText({
        shown: 12,
        laneTotal: 66,
        filtered: true,
        checkedAgo: 'sources checked 1h ago',
        hiddenNote: 'postings without a verifiable date are hidden',
      }),
    ).toBe(
      'Showing 12 of 66 jobs · sources checked 1h ago · postings without a verifiable date are hidden',
    );
    expect(
      filterStatusText({
        shown: 12,
        laneTotal: 66,
        filtered: true,
        checkedAgo: null,
        hiddenNote: 'postings without a verifiable date are hidden',
      }),
    ).toBe('Showing 12 of 66 jobs · postings without a verifiable date are hidden');
  });

  it('holds the clause back before the first page lands', () => {
    expect(
      filterStatusText({
        shown: undefined,
        laneTotal: undefined,
        filtered: true,
        checkedAgo: 'sources checked 1h ago',
        hiddenNote: 'postings without a verifiable date are hidden',
      }),
    ).toBe('sources checked 1h ago');
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

describe('pullReceipt', () => {
  const prefs = {
    roles: ['Data Engineering Manager', 'Staff Data Engineer'],
    preferred_places: [{ label: 'Los Angeles, CA' }],
    workplace_preference: 'remote_friendly',
    compensation: { min_base: 190000 },
  };

  it('names roles, place, remote stance, and pay floor', () => {
    expect(pullReceipt(prefs as never)).toBe(
      'Pulls fresh postings for Data Engineering Manager and 1 more role · Los Angeles, CA · remote friendly · $190K+ base.',
    );
  });

  it('says it ranks too when the assistant is ready', () => {
    expect(pullReceipt(prefs as never, true)).toBe(
      'Pulls fresh postings and ranks them for Data Engineering Manager and 1 more role · Los Angeles, CA · remote friendly · $190K+ base.',
    );
  });

  it('omits what is not saved', () => {
    expect(
      pullReceipt({
        roles: ['Staff Data Engineer'],
        preferred_places: [],
        workplace_preference: 'remote_only',
        compensation: { min_base: null },
      } as never),
    ).toBe('Pulls fresh postings for Staff Data Engineer · remote only.');
  });

  it('asks for roles when none are saved', () => {
    expect(
      pullReceipt({
        roles: [],
        preferred_places: [],
        workplace_preference: 'remote_friendly',
        compensation: { min_base: null },
      } as never),
    ).toBe('No target roles saved yet.');
  });

  it('holds the generic line while loading', () => {
    expect(pullReceipt(undefined)).toBe('Pulls fresh postings for your target roles.');
  });
});

describe('primaryRunKind', () => {
  it('runs the assistant when it is ready', () => {
    expect(primaryRunKind(true)).toBe('assistant');
  });

  it('falls back to a plain pull when the assistant is not ready', () => {
    expect(primaryRunKind(false)).toBe('pull');
  });
});

describe('filterStatusText scope note', () => {
  it('carries the pay scope next to the counts it explains', () => {
    expect(
      filterStatusText({
        shown: 632,
        laneTotal: 632,
        filtered: false,
        checkedAgo: 'sources checked minutes ago',
        scopeNote: '$190K+ base from your search',
      }),
    ).toBe('632 jobs · sources checked minutes ago · $190K+ base from your search');
  });

  it('keeps the posted confession last when both notes are set', () => {
    expect(
      filterStatusText({
        shown: 10,
        laneTotal: 40,
        filtered: true,
        checkedAgo: null,
        scopeNote: '$190K+ base from your search',
        hiddenNote: '3 without a date hidden',
      }),
    ).toBe('Showing 10 of 40 jobs · $190K+ base from your search · 3 without a date hidden');
  });

  it('reads exactly as before when no scope note applies', () => {
    expect(
      filterStatusText({ shown: 27, laneTotal: 27, filtered: false, checkedAgo: null }),
    ).toBe('27 jobs');
  });
});
