/* The pull's per-source results, read out of the run's own progress stream.

   A two-minute wait behind one spinner tells you nothing, and the run was
   already narrating itself: the scraper registry announces how many sources it
   is about to hit and then reports each one back as it lands. This turns that
   stream into a scoreboard. Everything here is parsed from what the run said;
   nothing is invented or estimated.

   Rows stay in the order the sources answered, which is the honest order and
   also the satisfying one: the quick sources land within a couple of seconds
   and the slow ones fill in behind them. */

export type SourceRunState = 'found' | 'empty' | 'timeout';

export interface SourceResult {
  source: string;
  count: number;
  state: SourceRunState;
}

export interface Scoreboard {
  rows: SourceResult[];
  /** how many sources have reported, answered or not */
  done: number;
  /** how many the run said it would hit, or null before it says */
  total: number | null;
}

const TOTAL_RE = /Searching (\d+) additional sources in parallel/;
const FOUND_RE = /^\s+Found (\d+) jobs? from (.+?)\s*$/;
const EMPTY_RE = /^\s+(.+?): no results\s*$/;
const TIMEOUT_RE = /^\s+(.+?): timed out\s*$/;

export function parseSourceScoreboard(messages: string[]): Scoreboard {
  let total: number | null = null;
  let rows: SourceResult[] = [];

  for (const msg of messages) {
    const batch = TOTAL_RE.exec(msg);
    if (batch) {
      // A second batch announcement means a fresh run; drop the old board
      // rather than stacking two runs' sources together.
      total = parseInt(batch[1], 10);
      rows = [];
      continue;
    }
    const found = FOUND_RE.exec(msg);
    if (found) {
      rows.push({ source: found[2], count: parseInt(found[1], 10), state: 'found' });
      continue;
    }
    const empty = EMPTY_RE.exec(msg);
    if (empty) {
      rows.push({ source: empty[1], count: 0, state: 'empty' });
      continue;
    }
    const timedOut = TIMEOUT_RE.exec(msg);
    if (timedOut) {
      rows.push({ source: timedOut[1], count: 0, state: 'timeout' });
    }
  }

  return { rows, done: rows.length, total };
}

/* Bar width as a share of the biggest haul so far, so the shape settles as
   results land instead of rescaling wildly off the first source home. Any
   source that found something keeps at least a sliver, or a real result reads
   as a blank line. */
export function barWidth(count: number, rows: SourceResult[]): number {
  if (count <= 0) return 0;
  const peak = Math.max(...rows.map((r) => r.count), 1);
  return Math.max(4, Math.round((count / peak) * 100));
}

/* The headline over the board. Honest before the run says how many sources it
   will hit, and never claims more done than the total. */
export function scoreboardHeadline({ done, total }: Scoreboard): string {
  if (total === null) return 'starting up';
  return `${Math.min(done, total)}/${total} sources`;
}
