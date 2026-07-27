/* The pull's scoreboard: every source the run touches, landing as it answers.

   A spinner for two minutes says nothing, and this run already narrates itself
   per source. Showing that stream makes the wait legible (you can watch it
   work), useful (a source that times out or comes back empty is visible right
   there), and it costs no new plumbing: the messages already arrive over SSE. */

import {
  barWidth,
  parseSourceScoreboard,
  scoreboardHeadline,
} from '@/features/board/source-scoreboard';

const STATE_WORD: Record<string, string> = {
  empty: 'nothing',
  timeout: 'timed out',
};

export function SourceScoreboard({ messages }: { messages: string[] }) {
  const board = parseSourceScoreboard(messages);
  if (board.rows.length === 0) return null;

  return (
    <div className="qb-scoreboard">
      <p className="qb-scoreboard-head">{scoreboardHeadline(board)}</p>
      <ul>
        {board.rows.map((row) => (
          <li key={row.source} className={`qb-score-row qb-score-${row.state}`}>
            <span className="qb-score-name">{row.source}</span>
            <span className="qb-score-count">
              {row.state === 'found' ? row.count : STATE_WORD[row.state]}
            </span>
            <span className="qb-score-bar" aria-hidden="true">
              <span style={{ width: `${barWidth(row.count, board.rows)}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
