/* An empty board has two honest explanations: the filters cut everything,
   or nothing has been fetched yet. The message must match the cause, so
   "clear a chip" never shows to a user who has no chips to clear. */

import { describe, expect, it } from 'vitest';
import { boardEmptyState, boardFiltersActive } from './board-empty';

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
  });

  it('ignores whitespace-only text', () => {
    expect(boardFiltersActive({ search: '   ', place: ' ', payFrom: ' ', payTo: ' ' })).toBe(false);
  });
});
