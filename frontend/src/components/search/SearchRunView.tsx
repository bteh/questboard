import type { RefObject } from 'react';
import { CheckCircle2, XCircle, Loader2, Sparkles, ArrowRight, Circle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PageHeader } from '@/components/layout/page-header';
import { PipelineSteps } from '@/components/shared/pipeline-steps';
import { ConnectAiPopover } from '@/components/onboarding/connect-ai-popover';
import { cn } from '@/lib/utils';
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
import { SnapshotField, SnapshotList } from './search-leaf';
import {
  MODE_LABELS,
  formatCurrency,
  formatElapsed,
  getStagesForMode,
  isStageComplete,
  titleCase,
} from './search-leaf-helpers';

interface SearchRunViewProps {
  state: 'idle' | 'running' | 'completed' | 'failed';
  activeStep: number | undefined;
  activeMode: SearchRequest['mode'];
  llmAvailable: boolean;
  sourceCount: number;
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
  activeStep,
  activeMode,
  llmAvailable,
  sourceCount,
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
  return (
    <div className="flex flex-col" style={{ minHeight: 'calc(100vh - 6rem)' }}>
      <PageHeader title="Run search" description="Search for jobs across multiple sources" />

      <div className="mb-6">
        <PipelineSteps
          llmAvailable={llmAvailable}
          activeStep={state === 'running' ? activeStep : state === 'completed' ? 3 : undefined}
          sourceCount={sourceCount}
        />
      </div>

      {/* Progress bar + stage dots */}
      {state === 'running' && (
        <div className="space-y-3 mb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
              <span className="text-sm font-medium text-text-primary">
                {progress?.stage_label || 'Starting...'}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-text-muted tabular-nums">
              <span>{progress?.percent ?? 0}%</span>
              <span>{formatElapsed(progress?.elapsed ?? 0)}</span>
              <Button onClick={handleReset} variant="ghost" size="sm" className="text-xs h-7 text-text-muted hover:text-danger">
                <XCircle className="h-3 w-3 mr-1" /> Cancel
              </Button>
            </div>
          </div>
          <Progress value={progress?.percent ?? 0} className="h-2" />
          <div className="flex items-center justify-between px-1">
            {getStagesForMode(activeMode).map((s) => {
              const isCurrent = stageForDisplay === s.key;
              const isDone = isStageComplete(s.key, stageForDisplay, activeMode);
              return (
                <div
                  key={s.key}
                  className={cn(
                    'flex items-center gap-1 text-[10px] transition-colors',
                    isCurrent ? 'text-brand font-medium' : isDone ? 'text-success' : 'text-text-muted',
                  )}
                >
                  {isDone ? <CheckCircle2 className="h-3 w-3" /> : isCurrent ? <Loader2 className="h-3 w-3 animate-spin" /> : <Circle className="h-3 w-3" />}
                  {s.label}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Result summary */}
      {result && (
        <div className="rounded-lg border border-success/30 bg-success/10 p-4 mb-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium text-success">Search Complete</p>
              <p className="text-xs text-text-secondary">
                Found {result.jobs_found} jobs · Scored {result.jobs_scored} · {result.strong_matches} strong matches · {(result.duration_seconds ?? 0).toFixed(1)}s
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={handleReset} variant="outline" size="sm">New search</Button>
              <Button size="sm" onClick={onViewJobs}>
                View {result.jobs_found} Jobs <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
              </Button>
            </div>
          </div>
          {result.sources && Object.keys(result.sources).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(result.sources)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => (
                  <span key={source} className="inline-flex items-center rounded-md bg-bg-card/70 px-2 py-0.5 text-[11px] text-text-secondary ring-1 ring-border-default">
                    {resolveSourceLabel(source, sourceLabels)}
                    <span className="ml-1 font-semibold tabular-nums">{count}</span>
                  </span>
                ))}
            </div>
          )}
          {funnel && !funnelDismissed && funnel.stages.length > 0 && (
            <FunnelSummary
              data={funnel}
              onDismiss={() => setFunnelDismissed(true)}
            />
          )}
          {snapshot && !snapshot.use_ai && (
            <div className="flex flex-col gap-3 rounded-lg border border-brand/20 bg-bg-card/70 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-text-primary">This run used basic ranking only.</p>
                <p className="mt-1 text-xs text-text-muted">
                  Connect AI to rerank by resume fit and unlock cover letters, company notes, and application prep.
                </p>
              </div>
              <ConnectAiPopover side="bottom" align="end">
                <Button variant="outline" size="sm" className="shrink-0">
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                  Connect AI
                </Button>
              </ConnectAiPopover>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-danger">Search Failed</p>
              <p className="text-xs text-text-secondary mt-1">
                {error.toLowerCase().includes('timeout')
                  ? 'The search took too long. Try searching with fewer locations or broader keywords.'
                  : error.toLowerCase().includes('fetch') || error.toLowerCase().includes('network')
                  ? 'We couldn\'t connect to the server. Please try again in a moment.'
                  : error}
              </p>
            </div>
            <Button onClick={handleReset} variant="outline" size="sm">Try Again</Button>
          </div>
        </div>
      )}

      {/* Full-width log — fills remaining viewport */}
      <div className="flex-1 min-h-[300px] rounded-lg border border-border-default bg-bg-card overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-bg-subtle">
          <span className="text-[11px] font-medium text-text-muted">Output log</span>
          <span className="text-[11px] text-text-muted tabular-nums">{messages.length} messages</span>
        </div>
        {snapshot && (
          <div className="border-b border-border-default bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.08),transparent_45%),linear-gradient(to_bottom,rgba(148,163,184,0.08),transparent)] px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-medium text-text-muted">Run settings</p>
                <p className="mt-1 text-sm font-medium text-text-primary">
                  {MODE_LABELS[snapshot.mode]} on profile <span className="text-brand">{snapshot.profile}</span>
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {snapshot.use_ai ? 'AI enabled' : 'Keyword only'}
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {getWorkplacePreferenceLabel(snapshot.workplace_preference)}
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {snapshot.max_days_old} day window
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  LinkedIn {snapshot.include_linkedin_jobs ? 'enabled' : 'disabled'}
                </span>
              </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_1fr]">
              <div className="space-y-3">
                <SnapshotList label="Roles" values={snapshot.roles} emptyLabel="None" />
                <SnapshotList label="Keywords" values={snapshot.keywords} emptyLabel="None" />
                <SnapshotList
                  label="Target companies"
                  values={snapshot.companies ?? []}
                  emptyLabel="None — searching job boards only"
                  hint="Searches these companies' ATS career pages (Greenhouse, Lever, Ashby, Workday) directly"
                />
                <SnapshotList
                  label="Locations"
                  values={snapshot.locations}
                  emptyLabel={snapshot.workplace_preference === 'remote_only' ? 'Remote only' : 'None'}
                />
              </div>

              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <SnapshotField label="Current title" value={snapshot.current_title || 'Not set'} />
                  <SnapshotField label="Current level" value={snapshot.current_level ? titleCase(snapshot.current_level) : 'Not set'} />
                  <SnapshotField label="Workplace" value={getWorkplacePreferenceLabel(snapshot.workplace_preference)} />
                  <SnapshotField
                    label="Match strictness"
                    value={titleCase(snapshot.match_strictness ?? 'balanced')}
                    hint="Loose pulls a wider net; Strict only surfaces tight matches"
                  />
                  <SnapshotField label="Currency" value={`${snapshot.compensation_currency} · ${snapshot.compensation_period}`} />
                  <SnapshotField label="Current TC" value={formatCurrency(snapshot.current_tc, snapshot.compensation_currency)} />
                  <SnapshotField label="Target TC" value={formatCurrency(snapshot.target_total_comp, snapshot.compensation_currency)} />
                  <SnapshotField
                    label="Min base"
                    value={formatCurrency(snapshot.min_base, snapshot.compensation_currency)}
                    hint="Floor on base salary (excludes bonus/equity)"
                  />
                  <SnapshotField
                    label="Min TC"
                    value={formatCurrency(snapshot.min_acceptable_tc, snapshot.compensation_currency)}
                    hint="Auto-skips jobs paying total comp below this"
                  />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                    Equity {snapshot.include_equity == null ? 'not set' : snapshot.include_equity ? 'included' : 'excluded'}
                  </span>
                  <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                    Staffing agencies {snapshot.exclude_staffing_agencies == null ? 'not set' : snapshot.exclude_staffing_agencies ? 'excluded' : 'allowed'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
        <ScrollArea className="flex-1">
          <div ref={logRef} className="p-4 space-y-0.5 font-mono text-xs">
            {messages.map((msg, i) => (
              <div key={i} className="text-text-secondary py-0.5 leading-relaxed">
                <span className="text-text-muted mr-2 tabular-nums select-none">[{String(i + 1).padStart(2, '0')}]</span>
                {msg}
              </div>
            ))}
            {state === 'running' && (
              <div className="text-brand animate-pulse py-0.5">Waiting for updates...</div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
