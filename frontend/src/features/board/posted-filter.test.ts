/* The shared date filter: a local-calendar first-seen day plus three rolling
   source-posted windows. Anything else means no additional date filter. */

import { describe, expect, it } from 'vitest';
import {
  POSTED_OPTIONS,
  hiddenDatesClause,
  normalizePostedDays,
  postedChipLabel,
  postedWithinDays,
  foundWithinDays,
} from './posted-filter';

describe('normalizePostedDays', () => {
  it('accepts the four windows however the router round-trips them', () => {
    // '1' left the vocabulary when posted-today merged into new-today.
    expect(normalizePostedDays('1')).toBeUndefined();
    expect(normalizePostedDays('3')).toBe('3');
    expect(normalizePostedDays('7')).toBe('7');
    expect(normalizePostedDays('30')).toBe('30');
    expect(normalizePostedDays(7)).toBe('7');
    expect(normalizePostedDays(30)).toBe('30');
  });

  it('drops anything outside the vocabulary', () => {
    expect(normalizePostedDays('0')).toBeUndefined();
    expect(normalizePostedDays('14')).toBeUndefined();
    expect(normalizePostedDays('')).toBeUndefined();
    expect(normalizePostedDays('week')).toBeUndefined();
    expect(normalizePostedDays(2)).toBeUndefined();
    expect(normalizePostedDays(null)).toBeUndefined();
    expect(normalizePostedDays(undefined)).toBeUndefined();
  });
});

describe('the posted select options', () => {
  it('offers the five windows in order, new today first', () => {
    expect(POSTED_OPTIONS.map((o) => o.value)).toEqual(['', 'found-1', '3', '7', '30']);
    expect(POSTED_OPTIONS.map((o) => o.label)).toEqual([
      'any time',
      'new today',
      'posted last 3 days',
      'posted last 7 days',
      'posted last 30 days',
    ]);
  });
});

describe('postedChipLabel', () => {
  it('names the active window in plain words', () => {
    expect(postedChipLabel('found-1')).toBe('new today');
    expect(postedChipLabel('3')).toBe('posted in the last 3 days');
    expect(postedChipLabel('7')).toBe('posted in the last 7 days');
    expect(postedChipLabel('30')).toBe('posted in the last 30 days');
  });
});

describe('postedWithinDays', () => {
  it('turns the URL value into the API number', () => {
    expect(postedWithinDays('7')).toBe(7);
    expect(postedWithinDays('30')).toBe(30);
    expect(postedWithinDays(undefined)).toBeUndefined();
  });
});

describe('the hidden-dates clause', () => {
  it('speaks while the filter is on and the count dropped', () => {
    expect(hiddenDatesClause({ days: '7', shown: 12, baseline: 66 })).toBe(
      'postings without a verifiable date are hidden',
    );
  });

  it('stays silent while the filter is off', () => {
    expect(hiddenDatesClause({ days: undefined, shown: 12, baseline: 66 })).toBeNull();
  });

  it('never blames missing post dates for the first-seen today filter', () => {
    expect(hiddenDatesClause({ days: 'found-1', shown: 12, baseline: 66 })).toBeNull();
  });

  it('stays silent while nothing dropped', () => {
    expect(hiddenDatesClause({ days: '7', shown: 66, baseline: 66 })).toBeNull();
    expect(hiddenDatesClause({ days: '7', shown: 70, baseline: 66 })).toBeNull();
  });

  it('stays silent while either count is still loading', () => {
    expect(hiddenDatesClause({ days: '7', shown: undefined, baseline: 66 })).toBeNull();
    expect(hiddenDatesClause({ days: '7', shown: 12, baseline: undefined })).toBeNull();
  });
});

describe('found today', () => {
  // The reader reached for "posted today" twice expecting "what arrived
  // today". Posted dates are the source's claim and often missing, so that
  // filter hid today's arrivals; found is our own clock and always set.
  it('is one of the options', () => {
    expect(POSTED_OPTIONS.some((o) => o.value === 'found-1')).toBe(true);
  });

  it('round-trips through the URL', () => {
    expect(normalizePostedDays('found-1')).toBe('found-1');
  });

  it('maps to the found window, not the posted one', () => {
    expect(postedWithinDays('found-1')).toBeUndefined();
    expect(foundWithinDays('found-1')).toBe(1);
    expect(foundWithinDays('3')).toBeUndefined();
  });

  it('has its own chip words', () => {
    expect(postedChipLabel('found-1')).toBe('new today');
  });
});
