import type { SourceHealthEntry } from '@/api/scrapers';
import { useLatestFunnel } from '@/hooks/use-search';
import { lastPullSummary } from './health-logic';

/* The most recent pull, digested: how many rows came in raw, what each
   filter kept and dropped, and which sources sent them. This is the funnel
   the old restock run view carried, moved to the diagnostics home. Renders
   nothing until a completed run has a funnel to show. */
export function LastPull({ sources }: { sources: SourceHealthEntry[] }) {
  const { data, isLoading } = useLatestFunnel();
  const stages = data?.stages ?? [];
  const summary = lastPullSummary(stages);

  if (isLoading || !summary) return null;

  const tallies = sources
    .filter((s) => s.last_rows > 0)
    .sort((a, b) => b.last_rows - a.last_rows);

  return (
    <section className="qb-health-card">
      <div className="qb-health-cardhead">
        <div>
          <h2>Last pull</h2>
          <p className="qb-health-cardsub">
            {summary.raw} found, {summary.kept} kept after filters.
          </p>
        </div>
      </div>
      <div className="qb-health-tablewrap">
        <table className="qb-health-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Kept</th>
              <th>Dropped</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((stage) => (
              <tr key={stage.key}>
                <td>{stage.label}</td>
                <td className="qb-health-num">
                  {stage.active ? (
                    stage.count_out
                  ) : (
                    <span className="qb-health-median">skipped</span>
                  )}
                </td>
                <td className="qb-health-num">
                  {stage.active && stage.dropped > 0 ? (
                    stage.dropped
                  ) : (
                    <span className="qb-health-median">0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {tallies.length > 0 && (
        <div className="qb-lastpull-sources">
          <div className="qb-health-cardsub">What each source sent</div>
          <ul>
            {tallies.map((s) => (
              <li key={s.source}>
                <span>{s.display_name}</span>
                <span className="qb-health-num">{s.last_rows}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
