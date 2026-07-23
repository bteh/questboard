import { describe, expect, it } from 'vitest';
import {
  agoLabel,
  durationLabel,
  filterRuns,
  healthTiles,
  lastPullSummary,
  reasonMeta,
  sourceOptions,
  verdictMeta,
} from './health-logic';

describe('verdictMeta', () => {
  it('speaks plain English with urgency as tone', () => {
    expect(verdictMeta('failing')).toEqual({ label: 'failing', tone: 'bad' });
    expect(verdictMeta('zero_rows')).toEqual({ label: 'went dark', tone: 'bad' });
    expect(verdictMeta('dropped')).toEqual({ label: 'volume dropped', tone: 'warn' });
    expect(verdictMeta('quiet')).toEqual({ label: 'quiet', tone: 'quiet' });
    expect(verdictMeta('ok')).toEqual({ label: 'ok', tone: 'ok' });
  });

  it('an unknown verdict falls back to ok, never crashes the page', () => {
    expect(verdictMeta('someday_new').tone).toBe('ok');
  });
});

describe('reasonMeta', () => {
  it('maps run outcomes', () => {
    expect(reasonMeta('exception')).toEqual({ label: 'error', tone: 'bad' });
    expect(reasonMeta('timeout')).toEqual({ label: 'timed out', tone: 'bad' });
    expect(reasonMeta('zero_rows')).toEqual({ label: 'no rows', tone: 'quiet' });
    expect(reasonMeta('ok')).toEqual({ label: 'ok', tone: 'ok' });
  });
});

describe('agoLabel', () => {
  const now = new Date('2026-07-10T12:00:00Z');

  it('treats naive ISO as UTC, same rule as the board freshness line', () => {
    expect(agoLabel('2026-07-10T11:00:00', now)).toBe('1h ago');
  });

  it('scales from minutes to days', () => {
    expect(agoLabel('2026-07-10T11:59:40Z', now)).toBe('just now');
    expect(agoLabel('2026-07-10T11:20:00Z', now)).toBe('40m ago');
    expect(agoLabel('2026-07-09T12:00:00Z', now)).toBe('24h ago');
    expect(agoLabel('2026-07-05T12:00:00Z', now)).toBe('5 days ago');
  });

  it('is honest about missing or broken timestamps', () => {
    expect(agoLabel(null, now)).toBe('never');
    expect(agoLabel('not a date', now)).toBe('never');
  });
});

describe('durationLabel', () => {
  it('formats short, medium, and long runs', () => {
    expect(durationLabel(2.53)).toBe('2.5s');
    expect(durationLabel(45)).toBe('45s');
    expect(durationLabel(95)).toBe('1m 35s');
  });

  it('empty for zero or garbage', () => {
    expect(durationLabel(0)).toBe('');
    expect(durationLabel(Number.NaN)).toBe('');
  });
});

const RUNS = [
  { source: 'remotive', display_name: 'Remotive', finish_reason: 'ok' },
  { source: 'remotive', display_name: 'Remotive', finish_reason: 'zero_rows' },
  { source: 'sittercity', display_name: 'Sittercity', finish_reason: 'exception' },
];

describe('filterRuns', () => {
  it('narrows by source, reason, or both; empty filters pass everything', () => {
    expect(filterRuns(RUNS, '', '')).toHaveLength(3);
    expect(filterRuns(RUNS, 'remotive', '')).toHaveLength(2);
    expect(filterRuns(RUNS, '', 'exception')).toHaveLength(1);
    expect(filterRuns(RUNS, 'remotive', 'exception')).toHaveLength(0);
  });
});

describe('sourceOptions', () => {
  it('dedups by source and sorts by label', () => {
    expect(sourceOptions(RUNS)).toEqual([
      { value: 'remotive', label: 'Remotive' },
      { value: 'sittercity', label: 'Sittercity' },
    ]);
  });
});

describe('healthTiles', () => {
  it('sums only the latest run per source and finds the newest check', () => {
    const tiles = healthTiles(
      [
        { last_rows: 28, last_run_at: '2026-07-10T11:00:00' },
        { last_rows: 0, last_run_at: '2026-07-10T11:30:00' },
        { last_rows: 5, last_run_at: null },
      ],
      1,
    );
    expect(tiles).toEqual({
      sources: 3,
      needsAttention: 1,
      rowsLatest: 33,
      lastChecked: '2026-07-10T11:30:00',
    });
  });

  it('handles the empty log', () => {
    expect(healthTiles([], 0)).toEqual({
      sources: 0,
      needsAttention: 0,
      rowsLatest: 0,
      lastChecked: null,
    });
  });
});

describe('lastPullSummary', () => {
  it('reads raw from the first stage in and kept from the last stage out', () => {
    const stages = [
      { count_in: 1080, count_out: 612 },
      { count_in: 612, count_out: 488 },
      { count_in: 488, count_out: 300 },
    ];
    expect(lastPullSummary(stages)).toEqual({ raw: 1080, kept: 300, dropped: 780 });
  });

  it('never reports a negative drop', () => {
    expect(lastPullSummary([{ count_in: 10, count_out: 12 }])).toEqual({
      raw: 10,
      kept: 12,
      dropped: 0,
    });
  });

  it('is null when no stage ran', () => {
    expect(lastPullSummary([])).toBeNull();
  });
});
