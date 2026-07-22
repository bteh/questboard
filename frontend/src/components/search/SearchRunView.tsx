import type { RefObject } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { getWorkplacePreferenceLabel } from '@/lib/profile-preferences';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { FunnelSummary } from '@/components/jobs/funnel-summary';
import type {
  FunnelSummary as FunnelSummaryData,
  ProgressUpdate,
  RunResult,
  SearchRequest,
  SearchRunSnapshot,
} from '@/types/search';
import { cx } from '@questboard/ui';
import { SnapshotField, SnapshotList } from './search-leaf';
import {
  MODE_LABELS,
  formatCurrency,
  formatElapsed,
  getStagesForMode,
  isStageComplete,
  titleCase,
} from './search-leaf-helpers';
import './restock.css';

/* The run view, trade paper: a hairline progress bar, mono stage row, the
   restock report as a paper card, and the raw output log underneath. When
   the run lands, the primary action is back to the board. */

interface SearchRunViewProps {
  state: 'idle' | 'running' | 'completed' | 'failed';
  activeMode: SearchRequest['mode'];
  progress: ProgressUpdate | null;
  stageForDisplay: string | undefined;
  result: RunResult | null;
  error: string | null;
  snapshot: SearchRunSnapshot | null;
  messages: string[];
  funnel: FunnelSummaryData | null;
  funnelDismissed: boolean;
  setFunnelDismissed: (value: boolean) => void;
  sourceLabels: Record<string, string>;
  logRef: RefObject<HTMLDivElement | null>;
  handleReset: () => void;
  onViewJobs: () => void;
}

export function SearchRunView({
  state,
  activeMode,
  progress,
  stageForDisplay,
  result,
  error,
  snapshot,
  messages,
  funnel,
  funnelDismissed,
  setFunnelDismissed,
  sourceLabels,
  logRef,
  handleReset,
  onViewJobs,
}: SearchRunViewProps) {
  const navigate = useNavigate();

  return (
    <div className="qb-restock" style={{ maxWidth: 820, margin: '0 auto', padding: '0 44px 96px' }}>
      <div className="qb-restock-head">
        <h1>{state === 'running' ? 'Restocking the board' : 'The restock report'}</h1>
        {state === 'running' && (
          <span className="qb-headnote">{formatElapsed(progress?.elapsed ?? 0)}</span>
        )}
      </div>

      {/* Progress bar and the stage row */}
      {state === 'running' && (
        <div style={{ marginTop: 10 }}>
          <div className="qb-runbar-row">
            <span className="qb-stagename">{progress?.stage_label || 'Starting...'}</span>
            <span className="qb-runnums">
              <span>{progress?.percent ?? 0}%</span>
              <button type="button" className="qb-plainbtn" style={{ fontSize: 13 }} onClick={handleReset}>
                Cancel
              </button>
            </span>
          </div>
          <div className="qb-runbar" role="progressbar" aria-valuenow={progress?.percent ?? 0} aria-valuemin={0} aria-valuemax={100}>
            <i style={{ width: `${progress?.percent ?? 0}%` }} />
          </div>
          <div className="qb-stages">
            {getStagesForMode(activeMode).map((s) => {
              const isCurrent = stageForDisplay === s.key;
              const isDone = isStageComplete(s.key, stageForDisplay, activeMode);
              return (
                <span key={s.key} className={cx(isCurrent && 'qb-on', isDone && 'qb-done')}>
                  {isDone ? 'done ' : ''}{s.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* The restock report */}
      {result && (
        <div className="qb-runcard">
          <h2>The board is restocked.</h2>
          <p className="qb-runmeta">
            {result.jobs_found} found, {result.jobs_scored} scored, {result.strong_matches} strong{' '}
            {result.strong_matches === 1 ? 'match' : 'matches'}, {(result.duration_seconds ?? 0).toFixed(1)}s
          </p>
          <div className="qb-runactions">
            <button
              type="button"
              className="qb-btn-sage"
              onClick={() => void navigate({ to: '/board' })}
            >
              Back to the board
            </button>
            <button type="button" className="qb-textlink" style={{ fontSize: 14 }} onClick={onViewJobs}>
              See the run in the ledger
            </button>
            <button type="button" className="qb-plainbtn" onClick={handleReset}>
              Restock again
            </button>
          </div>
          {result.sources && Object.keys(result.sources).length > 0 && (
            <div className="qb-srcledger">
              <div className="qb-fb-label">What each source sent</div>
              {Object.entries(result.sources)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => (
                  <div key={source} className="qb-fbrow">
                    <span>{resolveSourceLabel(source, sourceLabels)}</span>
                    <span className="qb-fpay">{count}</span>
                  </div>
                ))}
            </div>
          )}
          {funnel && !funnelDismissed && funnel.stages.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <FunnelSummary data={funnel} onDismiss={() => setFunnelDismissed(true)} />
            </div>
          )}
          {snapshot && !snapshot.use_ai && (
            <div className="qb-restock-note" style={{ marginTop: 14 }}>
              <b>This run ranked by keywords and filters.</b> Your connected assistant (Claude or
              Codex) can rank these by resume fit.
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="qb-runcard">
          <h2>The restock failed.</h2>
          <p style={{ fontSize: 14.5, color: 'var(--soft)', margin: '4px 0 0' }}>
            {error.toLowerCase().includes('timeout')
              ? 'It took too long. Try fewer places or broader keywords.'
              : error.toLowerCase().includes('fetch') || error.toLowerCase().includes('network')
              ? 'The backend could not be reached. Try again in a moment.'
              : error}
          </p>
          <div className="qb-runactions">
            <button type="button" className="qb-btn-sage" onClick={handleReset}>
              Try again
            </button>
          </div>
        </div>
      )}

      {/* The raw output log */}
      <div className="qb-runlog">
        <div className="qb-loghead">
          <span>Output log</span>
          <span className="qb-num">{messages.length} lines</span>
        </div>
        {snapshot && (
          <div className="qb-snapshot">
            <div className="qb-snaptitle">Run settings</div>
            <div className="qb-snapmode">
              {MODE_LABELS[snapshot.mode]} on profile <em>{snapshot.profile}</em>
            </div>
            <div className="qb-snapgrid">
              <SnapshotList label="Roles" values={snapshot.roles} emptyLabel="None" />
              <SnapshotList label="Keywords" values={snapshot.keywords} emptyLabel="None" />
              <SnapshotList
                label="Target companies"
                values={snapshot.companies ?? []}
                emptyLabel="None, job boards only"
                hint="Restocks these companies' career pages (Greenhouse, Lever, Ashby, Workday) directly"
              />
              <SnapshotList
                label="Locations"
                values={snapshot.locations}
                emptyLabel={snapshot.workplace_preference === 'remote_only' ? 'Remote only' : 'None'}
              />
              <SnapshotField label="Ranking" value={snapshot.use_ai ? 'AI resume fit' : 'Keyword only'} />
              <SnapshotField label="Workplace" value={getWorkplacePreferenceLabel(snapshot.workplace_preference)} />
              <SnapshotField label="Posted within" value={`${snapshot.max_days_old} days`} />
              <SnapshotField label="LinkedIn" value={snapshot.include_linkedin_jobs ? 'On' : 'Off'} />
              <SnapshotField label="Current title" value={snapshot.current_title || 'Not set'} />
              <SnapshotField label="Current level" value={snapshot.current_level ? titleCase(snapshot.current_level) : 'Not set'} />
              <SnapshotField
                label="Match strictness"
                value={titleCase(snapshot.match_strictness ?? 'balanced')}
                hint="Loose pulls a wider net; Strict keeps only tight matches"
              />
              <SnapshotField label="Currency" value={`${snapshot.compensation_currency}, ${snapshot.compensation_period}`} />
              <SnapshotField label="Current pay" value={formatCurrency(snapshot.current_tc, snapshot.compensation_currency)} />
              <SnapshotField label="Target pay" value={formatCurrency(snapshot.target_total_comp, snapshot.compensation_currency)} />
              <SnapshotField
                label="Min base salary"
                value={formatCurrency(snapshot.min_base, snapshot.compensation_currency)}
                hint="Floor on base salary, bonus and equity excluded"
              />
              <SnapshotField
                label="Min total pay"
                value={formatCurrency(snapshot.min_acceptable_tc, snapshot.compensation_currency)}
                hint="Skips jobs paying less than this in total"
              />
              <SnapshotField
                label="Equity"
                value={snapshot.include_equity == null ? 'Not set' : snapshot.include_equity ? 'Included' : 'Excluded'}
              />
              <SnapshotField
                label="Staffing agencies"
                value={snapshot.exclude_staffing_agencies == null ? 'Not set' : snapshot.exclude_staffing_agencies ? 'Excluded' : 'Allowed'}
              />
            </div>
          </div>
        )}
        <div ref={logRef} className="qb-logbody">
          {messages.map((msg, i) => (
            <div key={i}>
              <span className="qb-lineno">{String(i + 1).padStart(2, '0')}</span>
              {msg}
            </div>
          ))}
          {state === 'running' && <div className="qb-waitline">Waiting for the next line...</div>}
        </div>
      </div>
    </div>
  );
}
