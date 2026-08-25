/* An empty board has two honest explanations: the filters cut everything,
   or nothing has been fetched yet. The message must match the cause, so
   "clear a chip" never shows to a user who has no chips to clear. */

import { describe, expect, it } from 'vitest';
import { boardEmptyState, boardFiltersActive, trulyEmptyLines } from './board-empty';

describe('the board empty state', () => {
  it('reads as loaded while the count is unknown or positive', () => {
    expect(boardEmptyState(undefined, false)).toBe('loaded');
    expect(boardEmptyState(undefined, true)).toBe('loaded');
    expect(boardEmptyState(24, false)).toBe('loaded');
    expect(boardEmptyState(1, true)).toBe('loaded');
  });

  it('blames the filters only when a filter is actually set', () => {
    expect(boardEmptyState(0, true)).toBe('filtered-empty');
  });

  it('reads as truly empty when nothing is fetched and nothing is set', () => {
    expect(boardEmptyState(0, false)).toBe('truly-empty');
  });
});

describe('the first-run place answer on an empty database', () => {
  /* The audit's blocker: /start writes ?place=Austin, the database has zero
     rows and no source has ever run. The place is the ONE answer the app
     asked for, so it must not read back as a chip to clear. */
  it('never blames a filter before any source has been checked', () => {
    expect(boardEmptyState(0, true, true)).toBe('truly-empty');
  });

  it('still blames the filters once the sources have run', () => {
    expect(boardEmptyState(0, true, false)).toBe('filtered-empty');
  });

  it('never overrides a loaded board', () => {
    expect(boardEmptyState(12, true, true)).toBe('loaded');
    expect(boardEmptyState(undefined, false, true)).toBe('loaded');
  });
});

describe('the truly-empty board copy', () => {
  /* The backend fires its first sweep about 90 seconds after boot. Before
     that sweep the board is not broken, it is stocking itself, and the
     empty state must say so instead of staring back blank. */
  it('says the board is stocking itself before the first sweep', () => {
    const lines = trulyEmptyLines(true);
    expect(lines.lead).toContain('stocking itself');
    expect(lines.body).toContain('about a minute');
  });

  it('offers the manual check once a sweep has already run', () => {
    const lines = trulyEmptyLines(false);
    expect(lines.lead).toBe('The board is empty right now.');
    expect(lines.body).toContain('One check fills it');
  });
});

describe('what counts as an active filter', () => {
  it('sees nothing active on a bare board', () => {
    expect(boardFiltersActive({})).toBe(false);
    expect(
      boardFiltersActive({
        search: '',
        place: '',
        payFrom: '',
        payTo: '',
        facet: undefined,
        presetCount: 0,
        sourceCategory: null,
      }),
    ).toBe(false);
  });

  it('counts each filter on its own', () => {
    expect(boardFiltersActive({ search: 'juror' })).toBe(true);
    expect(boardFiltersActive({ place: 'Austin' })).toBe(true);
    expect(boardFiltersActive({ payFrom: '150' })).toBe(true);
    expect(boardFiltersActive({ payTo: '90k' })).toBe(true);
    expect(boardFiltersActive({ facet: 'pets' })).toBe(true);
    expect(boardFiltersActive({ presetCount: 1 })).toBe(true);
    expect(boardFiltersActive({ sourceCategory: 'gov' })).toBe(true);
    expect(boardFiltersActive({ postedDays: '7' })).toBe(true);
  });

  it('ignores whitespace-only text', () => {
    expect(boardFiltersActive({ search: '   ', place: ' ', payFrom: ' ', payTo: ' ' })).toBe(false);
  });
});
