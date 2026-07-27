import { useMemo, useRef, useState } from 'react';
import { createRoute, Link } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { Skeleton } from '@/components/ui/skeleton';
import { useScrapeRuns, useSourceHealth } from '@/hooks/use-scrapers';
import type { ScrapeRunEntry, SourceHealthEntry } from '@/api/scrapers';
import {
  agoLabel,
  durationLabel,
  filterRuns,
  healthTiles,
  reasonMeta,
  sourceOptions,
  verdictMeta,
} from '@/features/health/health-logic';
import { LastPull } from '@/features/health/last-pull';
import '@/features/health/health.css';

/* Source health: the ops page behind the board's "sources checked" line.
   Worst verdicts first from the API, then the raw run log to drill into.
   Not in the drawer; the doors in are the board legend and the URL. */

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/health',
  component: HealthPage,
});

const WINDOWS = [
  { days: 7, label: 'Last 7 days' },
  { days: 14, label: 'Last 14 days' },
  { days: 30, label: 'Last 30 days' },
] as const;

function Chip({ label, tone }: { label: string; tone: string }) {
  return (
    <span className="qb-health-chip" data-tone={tone}>
      {label}
    </span>
  );
}

function HealthRow({ entry, onDrill }: { entry: SourceHealthEntry; onDrill: (source: string) => void }) {
  const { label, tone } = verdictMeta(entry.verdict);
  return (
    <tr>
      <td>
        <button
          type="button"
          className="qb-health-srcbtn"
          onClick={() => onDrill(entry.source)}
          title="Show this source's runs"
        >
          {entry.display_name}
        </button>
      </td>
      {/* lane ids can carry underscores; the label reads as words */}
      <td className="qb-health-lane">{entry.vertical.replace(/_/g, ' ')}</td>
      <td><Chip label={label} tone={tone} /></td>
      <td className="qb-health-when">{agoLabel(entry.last_run_at)}</td>
      <td className="qb-health-num">
        {entry.last_rows}
        {/* one run has no history yet, so there is no honest "usual" */}
        {entry.runs_seen > 1 && (
          <span className="qb-health-median"> / {entry.median_rows} usual</span>
        )}
      </td>
      <td className="qb-health-num">{durationLabel(entry.last_seconds)}</td>
      <td className="qb-health-num">{entry.kept_rows}</td>
      <td className="qb-health-num">{entry.runs_seen}</td>
      <td className="qb-health-err" title={entry.error_sample || undefined}>
        {entry.error_sample}
      </td>
    </tr>
  );
}

function RunRow({ run }: { run: ScrapeRunEntry }) {
  const { label, tone } = reasonMeta(run.finish_reason);
  return (
    <tr>
      <td className="qb-health-when">{agoLabel(run.started_at)}</td>
      <td className="qb-health-source">{run.display_name}</td>
      <td><Chip label={label} tone={tone} /></td>
      <td className="qb-health-num">{run.rows_found}</td>
      <td className="qb-health-num">
        {run.rows_invalid > 0
          ? <span className="qb-health-chip" data-tone="warn">{run.rows_invalid}</span>
          : <span className="qb-health-median">0</span>}
      </td>
      <td className="qb-health-num">{durationLabel(run.duration_s)}</td>
      <td className="qb-health-err" title={run.error_sample || undefined}>
        {run.error_sample}
      </td>
    </tr>
  );
}

function HealthPage() {
  const [days, setDays] = useState<number>(14);
  const [runSource, setRunSource] = useState('');
  const [runReason, setRunReason] = useState('');
  const runsCardRef = useRef<HTMLElement>(null);

  const health = useSourceHealth(days);
  const runsQuery = useScrapeRuns(days);

  const entries = health.data?.sources ?? [];
  const tiles = healthTiles(entries, health.data?.needs_attention ?? 0);
  const allRuns = runsQuery.data?.runs ?? [];
  const runs = filterRuns(allRuns, runSource, runReason);
  const sources = useMemo(() => sourceOptions(allRuns), [allRuns]);
  const reasons = useMemo(
    () => [...new Set(allRuns.map((r) => r.finish_reason))].sort(),
    [allRuns],
  );

  const drillTo = (source: string) => {
    setRunSource(source);
    runsCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const loading = health.isLoading || runsQuery.isLoading;
  const nothingLogged = !loading && entries.length === 0;

  return (
    <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 44px 96px' }}>
      <div className="qb-health-head">
        <Link to="/board" className="qb-textlink" style={{ fontSize: 13.5 }}>
          The board
        </Link>
        <div className="qb-health-headrow">
          <div>
            <h1>Source health</h1>
            <p className="qb-health-sub">
              Every fetch leaves a record. Sources that broke rise to the top.
            </p>
          </div>
          <select
            className="qb-health-ctl"
            aria-label="Run-log window"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {WINDOWS.map((w) => (
              <option key={w.days} value={w.days}>{w.label}</option>
            ))}
          </select>
        </div>
      </div>

      {nothingLogged ? (
        <p style={{ fontSize: 14.5, color: 'var(--soft)' }}>
          No runs logged in this window yet. Restock the board once and this page fills in.
        </p>
      ) : (
        <>
          <div className="qb-health-kpirow">
            {health.isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="qb-health-kpi"><Skeleton className="h-10 w-full" /></div>
              ))
            ) : (
              <>
                <div className="qb-health-kpi">
                  <div className="qb-health-kpival">{tiles.sources}</div>
                  <div className="qb-health-kpilab">sources checked</div>
                </div>
                <div className="qb-health-kpi">
                  <div className="qb-health-kpival" data-tone={tiles.needsAttention > 0 ? 'bad' : 'ok'}>
                    {tiles.needsAttention}
                  </div>
                  <div className="qb-health-kpilab">need attention</div>
                </div>
                <div className="qb-health-kpi">
                  <div className="qb-health-kpival">{tiles.rowsLatest}</div>
                  <div className="qb-health-kpilab">rows, latest runs</div>
                </div>
                <div className="qb-health-kpi">
                  <div className="qb-health-kpival">{agoLabel(tiles.lastChecked)}</div>
                  <div className="qb-health-kpilab">last check</div>
                </div>
              </>
            )}
          </div>

          <LastPull sources={entries} />

          <section className="qb-health-card">
            <div className="qb-health-cardhead">
              <div>
                <h2>The sources</h2>
                <p className="qb-health-cardsub">
                  Each source judged against its own recent history, worst first.
                </p>
              </div>
            </div>
            <div className="qb-health-tablewrap">
              <table className="qb-health-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Lane</th>
                    <th>Verdict</th>
                    <th>Last run</th>
                    <th>Rows</th>
                    {/* what it costs against what survives YOUR search. A big
                        gap is a matter of fit, never a health verdict: the
                        same source can be someone else's best one. */}
                    <th title="Wall-clock for the latest run">Took</th>
                    <th title="Rows from this source still on your board">Kept for you</th>
                    <th>Runs</th>
                    <th>What broke</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <HealthRow key={e.source} entry={e} onDrill={drillTo} />
                  ))}
                </tbody>
              </table>
              {health.isLoading && <div className="qb-health-empty">Reading the run log…</div>}
            </div>
          </section>

          <section className="qb-health-card" ref={runsCardRef}>
            <div className="qb-health-cardhead">
              <div>
                <h2>Run log</h2>
                <p className="qb-health-cardsub">Every fetch in the window, newest first.</p>
              </div>
              <div className="qb-health-ctlrow">
                <select
                  className="qb-health-ctl"
                  aria-label="Filter by source"
                  value={runSource}
                  onChange={(e) => setRunSource(e.target.value)}
                >
                  <option value="">All sources</option>
                  {sources.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
                <select
                  className="qb-health-ctl"
                  aria-label="Filter by outcome"
                  value={runReason}
                  onChange={(e) => setRunReason(e.target.value)}
                >
                  <option value="">All outcomes</option>
                  {reasons.map((r) => (
                    <option key={r} value={r}>{reasonMeta(r).label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="qb-health-tablewrap">
              <table className="qb-health-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Source</th>
                    <th>Outcome</th>
                    <th>Rows</th>
                    <th>Rejected</th>
                    <th>Took</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run, i) => (
                    <RunRow key={`${run.source}-${run.started_at}-${i}`} run={run} />
                  ))}
                </tbody>
              </table>
              {!runsQuery.isLoading && runs.length === 0 && (
                <div className="qb-health-empty">No runs match these filters.</div>
              )}
              {runsQuery.isLoading && <div className="qb-health-empty">Reading the run log…</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
