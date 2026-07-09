import { describe, expect, it } from 'vitest';
import {
  restockAgeDays,
  restockLine,
  restockProgress,
  restockedWhen,
} from './restock-logic';

/* Fixed clock: 2026-07-08 18:00 UTC. */
const NOW = new Date('2026-07-08T18:00:00Z');

/** date_found the way the pipeline stores it: naive UTC with a space. */
function dateFound(daysAgo: number): string {
  const d = new Date(NOW.getTime() - daysAgo * 86_400_000);
  return d.toISOString().replace('T', ' ').replace('Z', '');
}

describe('restockAgeDays', () => {
  it('reads the pipeline date shape as UTC', () => {
    expect(restockAgeDays('2026-07-08 12:24:34.011027', NOW)).toBe(0);
    expect(restockAgeDays('2026-07-05 18:30:00', NOW)).toBe(2);
  });

  it('accepts ISO strings too', () => {
    expect(restockAgeDays('2026-07-07T17:00:00Z', NOW)).toBe(1);
  });

  it('returns null for missing or unreadable dates', () => {
    expect(restockAgeDays(null, NOW)).toBeNull();
    expect(restockAgeDays(undefined, NOW)).toBeNull();
    expect(restockAgeDays('', NOW)).toBeNull();
    expect(restockAgeDays('not a date', NOW)).toBeNull();
  });

  it('never goes negative on a clock skewed row', () => {
    expect(restockAgeDays('2026-07-09 02:00:00', NOW)).toBe(0);
  });
});

describe('restockLine', () => {
  it('reads today for a fresh restock', () => {
    expect(restockLine(dateFound(0), NOW)).toEqual({ kind: 'fresh', label: 'today' });
  });

  it('reads yesterday', () => {
    expect(restockLine(dateFound(1), NOW)).toEqual({ kind: 'fresh', label: 'yesterday' });
  });

  it('counts the days inside the week', () => {
    expect(restockLine(dateFound(3), NOW)).toEqual({ kind: 'fresh', label: '3 days ago' });
    expect(restockLine(dateFound(6), NOW)).toEqual({ kind: 'fresh', label: '6 days ago' });
  });

  it('goes stale at seven days', () => {
    expect(restockLine(dateFound(7), NOW)).toEqual({ kind: 'stale' });
    expect(restockLine(dateFound(30), NOW)).toEqual({ kind: 'stale' });
  });

  it('an empty board is stale, never a guessed date', () => {
    expect(restockLine(null, NOW)).toEqual({ kind: 'stale' });
    expect(restockLine('garbage', NOW)).toEqual({ kind: 'stale' });
  });
});

describe('restockedWhen', () => {
  it('speaks plainly', () => {
    expect(restockedWhen(0)).toBe('today');
    expect(restockedWhen(1)).toBe('yesterday');
    expect(restockedWhen(5)).toBe('5 days ago');
  });
});

describe('restockProgress', () => {
  it('is null before the sources are announced', () => {
    expect(restockProgress([])).toBeNull();
    expect(restockProgress(['Searching 12 role combos in parallel...'])).toBeNull();
  });

  it('counts each source reporting back, in all three line shapes', () => {
    const messages = [
      'Searching 5 additional sources in parallel...',
      '  Found 12 jobs from Remotive',
      '  Himalayas: no results',
      '  We Work Remotely: timed out',
    ];
    expect(restockProgress(messages)).toEqual({ done: 3, total: 5 });
  });

  it('ignores unrelated log lines', () => {
    const messages = [
      'Searching 3 additional sources in parallel...',
      'Quick-scoring 40 jobs...',
      '  Found 4 jobs from RemoteOK',
    ];
    expect(restockProgress(messages)).toEqual({ done: 1, total: 3 });
  });

  it('never counts past the announced total', () => {
    const messages = [
      'Searching 1 additional sources in parallel...',
      '  Found 4 jobs from RemoteOK',
      '  Found 2 jobs from Remotive',
    ];
    expect(restockProgress(messages)).toEqual({ done: 1, total: 1 });
  });

  it('a fresh announcement restarts the count', () => {
    const messages = [
      'Searching 2 additional sources in parallel...',
      '  Found 4 jobs from RemoteOK',
      'Searching 6 additional sources in parallel...',
      '  Found 1 jobs from Remotive',
    ];
    expect(restockProgress(messages)).toEqual({ done: 1, total: 6 });
  });
});
