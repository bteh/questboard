import { describe, expect, it } from 'vitest';

import {
  barWidth,
  parseSourceScoreboard,
  scoreboardHeadline,
} from '@/features/board/source-scoreboard';

/* Verbatim shapes from src/job_finder/tools/scrapers/_registry.py. If those
   strings change, these tests are what tells you the scoreboard went blank. */
const BATCH = 'Searching 17 additional sources in parallel...';
const found = (n: number, name: string) => `  Found ${n} jobs from ${name}`;
const empty = (name: string) => `  ${name}: no results`;
const timedOut = (name: string) => `  ${name}: timed out`;

describe('parseSourceScoreboard', () => {
  it('reads a source and its haul out of the run stream', () => {
    const board = parseSourceScoreboard([BATCH, found(500, 'Lever')]);
    expect(board.rows).toEqual([{ source: 'Lever', count: 500, state: 'found' }]);
    expect(board.total).toBe(17);
    expect(board.done).toBe(1);
  });

  it('keeps the order the sources answered in', () => {
    // Real shape of a run: the quick ones land first, slow ones fill in behind.
    const board = parseSourceScoreboard([
      BATCH,
      found(1, 'RemoteOK'),
      found(26, 'Hacker News'),
      found(500, 'Ashby'),
    ]);
    expect(board.rows.map((r) => r.source)).toEqual(['RemoteOK', 'Hacker News', 'Ashby']);
  });

  it('records a source that answered with nothing', () => {
    const board = parseSourceScoreboard([BATCH, empty('The Muse')]);
    expect(board.rows).toEqual([{ source: 'The Muse', count: 0, state: 'empty' }]);
  });

  it('records a source that timed out, rather than dropping it', () => {
    const board = parseSourceScoreboard([BATCH, timedOut('Workday')]);
    expect(board.rows).toEqual([{ source: 'Workday', count: 0, state: 'timeout' }]);
  });

  it('handles the singular, which the run emits for one job', () => {
    const board = parseSourceScoreboard([BATCH, '  Found 1 job from Remotive']);
    expect(board.rows[0]).toEqual({ source: 'Remotive', count: 1, state: 'found' });
  });

  it('starts a clean board when a second run begins', () => {
    const board = parseSourceScoreboard([
      BATCH,
      found(500, 'Lever'),
      BATCH,
      found(26, 'Hacker News'),
    ]);
    expect(board.rows).toEqual([{ source: 'Hacker News', count: 26, state: 'found' }]);
    expect(board.done).toBe(1);
  });

  it('ignores chatter that is not a source result', () => {
    const board = parseSourceScoreboard([
      'Reading your resume',
      BATCH,
      '  Greenhouse: discovered 12 new companies (watchlist now 155)',
      found(87, 'Greenhouse'),
      'Warning: some scrapers timed out, using partial results',
    ]);
    expect(board.rows).toEqual([{ source: 'Greenhouse', count: 87, state: 'found' }]);
  });

  it('is empty, not broken, before the run says anything', () => {
    expect(parseSourceScoreboard([])).toEqual({ rows: [], done: 0, total: null });
  });
});

describe('scoreboardHeadline', () => {
  it('counts sources home against the announced total', () => {
    expect(scoreboardHeadline({ rows: [], done: 9, total: 17 })).toBe('9/17 sources');
  });

  it('never claims more done than the run said it would run', () => {
    expect(scoreboardHeadline({ rows: [], done: 20, total: 17 })).toBe('17/17 sources');
  });

  it('says so plainly before the total is known', () => {
    expect(scoreboardHeadline({ rows: [], done: 0, total: null })).toBe('starting up');
  });
});

describe('barWidth', () => {
  const rows = [
    { source: 'RemoteOK', count: 1, state: 'found' as const },
    { source: 'Ashby', count: 500, state: 'found' as const },
  ];

  it('scales against the biggest haul so far', () => {
    expect(barWidth(500, rows)).toBe(100);
    expect(barWidth(250, rows)).toBe(50);
  });

  it('leaves a sliver for a small but real result', () => {
    // 1/500 rounds to 0%, which would render a real source as a blank line.
    expect(barWidth(1, rows)).toBe(4);
  });

  it('gives an empty or timed-out source no bar at all', () => {
    expect(barWidth(0, rows)).toBe(0);
  });

  it('does not divide by zero on an all-empty board', () => {
    expect(barWidth(0, [])).toBe(0);
  });
});
