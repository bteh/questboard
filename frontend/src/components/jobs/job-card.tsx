import { useState, useMemo } from 'react';
import { ExternalLink, ChevronDown, MapPin, Send, CheckCircle2, AlertTriangle, Trash2, ThumbsUp, ThumbsDown, BadgeCheck, ListChecks } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CompanyAvatar } from '@/components/shared/company-avatar';
import { ScoreCircle } from '@/components/scores/score-circle';
import { RecommendationBadge } from '@/components/badges/recommendation-badge';
import { CompanyTypeBadge } from '@/components/badges/company-type-badge';
import { WorkTypeBadge } from '@/components/badges/work-type-badge';
import { FundingBadge } from '@/components/badges/funding-badge';
import { JobDetail } from './job-detail';
import { ApplyDrawer } from './apply-drawer';
import { useDeleteApplication, useUpdateFeedback } from '@/hooks/use-applications';
import { truncateDescription, formatDate, formatSalary } from '@/utils/format';
import { classifyFreshness, postedAgoLabel, staleWarning, type Freshness } from '@/utils/job-trust';
import { computeRequirementFit } from '@/utils/job-fit';
import { cn } from '@/lib/utils';
import type { EvaluationReport } from '@/types/application';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { toast } from 'sonner';
import { SCORE_DIMENSIONS } from '@/utils/constants';
import { scoreColorHex } from '@/utils/colors';
import type { ApplicationResponse } from '@/types/application';

const REC_BORDER_COLORS: Record<string, string> = {
  STRONG_APPLY: 'var(--lb-success)',
  APPLY: 'var(--lb-brand)',
  MAYBE: 'var(--lb-warning)',
  SKIP: 'var(--lb-border-default)',
};

function getRecencyLabel(dateFound: string | null | undefined): string | null {
  if (!dateFound) return null;
  const hours = (Date.now() - new Date(dateFound).getTime()) / 3600000;
  if (hours < 24) return 'Today';
  if (hours < 168) return 'This week';
  return null;
}

// Color the true-post-date label by age. Fresh/recent stay quiet (muted with a
// green dot) so the card doesn't shout; only aging/stale go amber to warn.
const FRESHNESS_DOT: Record<Freshness, string> = {
  fresh: 'bg-success',
  recent: 'bg-success/60',
  aging: 'bg-warning',
  stale: 'bg-warning',
  unknown: 'bg-text-faint',
};

interface JobCardProps {
  app: ApplicationResponse;
  sourceLabels?: Record<string, string>;
  // Used to badge truly-new jobs in the latest run. When app.first_seen_run_id
  // matches this, the card shows a "New" chip in the meta row.
  latestRunId?: string | null;
}

/** Color classes for inline score breakdown bars. */
/**
 * Compact, expandable narrative for the "Why this score" paragraph.
 * AI output is often paragraph-length; default to a 2-line clamp so the
 * card stays scannable. Click anywhere on the text to reveal the full text.
 */
function ScoreReasoning({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  // Looks long when there's more than ~180 chars or any newlines — anything
  // shorter probably fits in 2 lines anyway.
  const isLong = text.length > 180 || text.includes('\n');
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-text-secondary">Why this score</p>
        {isLong && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
            className="text-[11px] text-text-tertiary hover:text-text-secondary underline-offset-2 hover:underline"
          >
            {expanded ? 'Show less' : 'Show all'}
          </button>
        )}
      </div>
      <p
        className={cn(
          'text-xs text-text-secondary leading-relaxed whitespace-pre-line',
          isLong && !expanded && 'line-clamp-2',
        )}
        title={isLong && !expanded ? text : undefined}
      >
        {text}
      </p>
    </div>
  );
}

/**
 * Bullet list of strengths or gaps. Caps to 3 items by default with a
 * "+N more" toggle, and clamps each bullet to 2 lines so verbose AI
 * outputs don't dominate the card.
 */
function ScoreBulletList({
  label,
  labelClass,
  prefix,
  items,
}: {
  label: string;
  labelClass: string;
  prefix: string;
  items: string[];
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? items : items.slice(0, 3);
  const hidden = items.length - visible.length;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className={cn('text-xs font-medium', labelClass)}>{label}</p>
        {(hidden > 0 || showAll) && items.length > 3 && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowAll((v) => !v); }}
            className="text-[11px] text-text-tertiary hover:text-text-secondary underline-offset-2 hover:underline"
          >
            {showAll ? 'Show less' : `+${hidden} more`}
          </button>
        )}
      </div>
      <ul className="space-y-1">
        {visible.map((item, i) => (
          <li
            key={i}
            className="text-xs text-text-secondary leading-relaxed line-clamp-2"
            title={item}
          >
            <span className="mr-1 text-text-tertiary">{prefix}</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function scoreBgClass(value: number | null): string {
  if (value == null) return 'bg-bg-muted';
  if (value > 60) return 'bg-success';
  if (value >= 40) return 'bg-warning';
  return 'bg-danger';
}

export function JobCard({ app, sourceLabels, latestRunId }: JobCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isNewInLatestRun =
    !!latestRunId && app.first_seen_run_id != null && app.first_seen_run_id === latestRunId;
  const [applyOpen, setApplyOpen] = useState(false);
  const deleteApp = useDeleteApplication();
  const updateFeedback = useUpdateFeedback();
  const labels = sourceLabels;
  const isApplied = app.status === 'applied';
  const feedback = app.user_feedback || '';

  const sendFeedback = (next: 'up' | 'down') => {
    const value: 'up' | 'down' | '' = feedback === next ? '' : next;
    updateFeedback.mutate(
      { id: app.id, data: { feedback: value } },
      {
        onError: () => toast.error('Failed to save feedback'),
      },
    );
  };

  const borderColor = REC_BORDER_COLORS[app.recommendation] || REC_BORDER_COLORS.SKIP;
  const recency = getRecencyLabel(app.date_found);
  const salaryText = formatSalary(app.salary_min, app.salary_max);

  // Trust & freshness: the TRUE original post date (not when we found it) so a
  // months-old repost can't look fresh. Falls back to date_found recency.
  const postedAgo = postedAgoLabel(app.date_posted, app.date_confidence);
  const freshness = classifyFreshness(app.date_posted, app.date_confidence);
  const staleNote = staleWarning(app.date_posted, app.date_confidence);
  const isDirect = !!app.direct_from_company;

  // Honest fit: "you cover N of M requirements" from the full evaluation, when
  // one exists (STRONG_APPLY/APPLY jobs). Parsed lazily; empty for the rest.
  const fit = useMemo(() => {
    if (!app.evaluation_report_json) return null;
    try {
      return computeRequirementFit(JSON.parse(app.evaluation_report_json) as EvaluationReport);
    } catch {
      return null;
    }
  }, [app.evaluation_report_json]);

  return (
    <Card
      className={cn(
        'overflow-hidden border-l-[3px] transition-all duration-150 group',
        !expanded && 'hover:shadow-md hover:-translate-y-[1px]',
        expanded && 'shadow-md',
      )}
      style={{ borderLeftColor: borderColor }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${app.job_title} at ${app.company}, ${expanded ? 'collapse' : 'expand'} details`}
        className="flex items-start gap-4 p-5 w-full text-left cursor-pointer select-none focus-ring rounded-lg"
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(!expanded); } }}
      >
        <CompanyAvatar company={app.company} size={48} />

        <div className="flex-1 min-w-0">
          {/* Title row — title and salary share top-line emphasis */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-text-primary leading-snug truncate">{app.job_title}</h3>
              <p className="text-sm text-text-secondary mt-0.5">
                <span className="font-medium text-text-primary">{app.company}</span>
                {app.location && (
                  <span className="inline-flex items-center gap-1 text-text-tertiary ml-1.5">
                    <span>·</span>
                    <MapPin className="h-3 w-3 shrink-0" />
                    {app.location}
                    {app.work_type === 'remote' && <span className="text-brand font-medium">(Remote)</span>}
                    {app.work_type === 'hybrid' && <span className="text-warning font-medium">(Hybrid)</span>}
                  </span>
                )}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {salaryText && (
                <span className="flex flex-col items-end">
                  <span className="text-sm font-semibold text-success tabular-nums whitespace-nowrap">
                    {salaryText}
                  </span>
                  {app.salary_source === 'parsed_from_description' && (
                    <span
                      title="This range was parsed from the job description text, not reported by the employer."
                      className="text-[10px] leading-tight text-text-muted whitespace-nowrap"
                    >
                      estimated from description
                    </span>
                  )}
                </span>
              )}
              <ScoreCircle score={app.overall_score} />
              <ChevronDown
                className={cn(
                  'h-4 w-4 text-text-muted transition-transform duration-150',
                  expanded && 'rotate-180',
                )}
              />
            </div>
          </div>

          {/* Description preview */}
          {app.description && (
            <p className="mt-2 text-sm text-text-tertiary line-clamp-2 leading-relaxed">
              {truncateDescription(app.description, 220)}
            </p>
          )}

          {/* Slim badge row — primary signals only. Company-type and funding
              live in the expanded detail to keep the card scannable. */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <RecommendationBadge recommendation={app.recommendation} />
            <WorkTypeBadge workType={app.work_type} isRemote={app.is_remote} />
            {isDirect && (
              <span
                title="Links straight to the company's own careers page. You apply direct, with no aggregator in between."
                className="inline-flex items-center gap-1 rounded-md border border-success/25 bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success"
              >
                <BadgeCheck className="h-3 w-3" />
                Direct
              </span>
            )}
            {app.source && (
              <span className="inline-flex items-center rounded-md bg-bg-subtle border border-border-default px-2 py-0.5 text-[11px] font-medium text-text-secondary">
                {resolveSourceLabel(app.source, labels)}
              </span>
            )}
            {fit && (
              <span
                title={`Your resume covers ${fit.strong} of ${fit.total} of this job's stated requirements`}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium',
                  fit.ratio >= 0.6
                    ? 'border-success/25 bg-success/10 text-success'
                    : 'border-warning/40 bg-warning/10 text-warning',
                )}
              >
                <ListChecks className="h-3 w-3" />
                Covers {fit.strong}/{fit.total}
              </span>
            )}
            <CompanyTypeBadge companyType={app.company_type} />
            <FundingBadge app={app} />
          </div>

          {/* Action row */}
          <div className="mt-3 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            {isApplied ? (
              <span className="inline-flex items-center gap-1.5 rounded-md bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Applied
              </span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setApplyOpen(true);
                }}
                className="gap-1.5"
              >
                <Send className="h-3.5 w-3.5" />
                Apply
              </Button>
            )}
            <div className="flex items-center gap-1 ml-1">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); sendFeedback('up'); }}
                disabled={updateFeedback.isPending}
                className={cn(
                  'inline-flex items-center justify-center h-8 w-8 min-h-[44px] min-w-[44px] rounded-md transition-colors cursor-pointer focus-ring',
                  feedback === 'up'
                    ? 'text-success bg-success/10'
                    : 'text-text-muted hover:text-success hover:bg-success/10',
                )}
                title={feedback === 'up' ? 'You liked this — click to clear' : 'Good match'}
                aria-label={feedback === 'up' ? 'Liked — clear feedback' : 'Mark as a good match'}
                aria-pressed={feedback === 'up'}
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); sendFeedback('down'); }}
                disabled={updateFeedback.isPending}
                className={cn(
                  'inline-flex items-center justify-center h-8 w-8 min-h-[44px] min-w-[44px] rounded-md transition-colors cursor-pointer focus-ring',
                  feedback === 'down'
                    ? 'text-danger bg-danger/10'
                    : 'text-text-muted hover:text-danger hover:bg-danger/10',
                )}
                title={feedback === 'down' ? 'You disliked this — click to clear' : 'Not a match'}
                aria-label={feedback === 'down' ? 'Disliked — clear feedback' : 'Mark as not a match'}
                aria-pressed={feedback === 'down'}
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                deleteApp.mutate(app.id, {
                  onSuccess: () => toast.success(`Removed ${app.job_title}`),
                  onError: () => toast.error('Failed to delete job'),
                });
              }}
              disabled={deleteApp.isPending}
              className="ml-auto inline-flex items-center justify-center h-8 w-8 min-h-[44px] min-w-[44px] rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors opacity-60 group-hover:opacity-100 focus-visible:opacity-100 cursor-pointer focus-ring"
              title="Remove job"
              aria-label={`Remove ${app.job_title}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Meta footer — date, employees, link out. Source already shown
              in the badge row above to call out where the listing came from. */}
          <div className="mt-2 flex items-center gap-3 text-xs text-text-muted">
            {isNewInLatestRun && (
              <span
                className="inline-flex items-center rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-success"
                title="First surfaced by your most recent search"
              >
                New
              </span>
            )}
            {/* True original post date (not when we found it) — a repost can't
                reset this. Fresh/recent stay quiet; aging/stale go amber. */}
            {postedAgo ? (
              <span
                className={cn(
                  'inline-flex items-center gap-1.5',
                  (freshness === 'aging' || freshness === 'stale') && 'text-warning',
                )}
                title={
                  staleNote
                    ? `${postedAgo} on the source board. ${staleNote}.`
                    : `${postedAgo} on the source board`
                }
              >
                <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', FRESHNESS_DOT[freshness])} />
                {postedAgo}
                {freshness === 'stale' && (
                  <span className="inline-flex items-center gap-1 font-medium">
                    <AlertTriangle className="h-3 w-3" />
                    may be filled
                  </span>
                )}
              </span>
            ) : recency ? (
              <span>{recency}</span>
            ) : app.date_found ? (
              <span>{formatDate(app.date_found, 'relative')}</span>
            ) : null}
            {app.employee_count && <span>{app.employee_count} employees</span>}
            {app.job_url && (
              app.url_status === 'dead' ? (
                <span className="inline-flex items-center gap-1 text-danger text-[11px]">
                  <AlertTriangle className="h-3 w-3" />
                  Expired
                </span>
              ) : (
                <a
                  href={app.job_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-brand hover:text-brand-hover transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="h-3 w-3" />
                  {isDirect ? 'Apply on company site' : 'View posting'}
                </a>
              )
            )}
          </div>
        </div>
      </div>

      {expanded && app.overall_score != null && (
        <div className="border-t border-border-default bg-bg-subtle px-5 py-4 space-y-4" onClick={(e) => e.stopPropagation()}>
          {app.score_reasoning && (
            <ScoreReasoning text={app.score_reasoning} />
          )}
          {(app.key_strengths?.length || app.key_gaps?.length) ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {app.key_strengths?.length ? (
                <ScoreBulletList
                  label="Strengths"
                  labelClass="text-success"
                  prefix="+"
                  items={app.key_strengths}
                />
              ) : null}
              {app.key_gaps?.length ? (
                <ScoreBulletList
                  label="Room to grow"
                  labelClass="text-warning"
                  prefix={'\u2212'}
                  items={app.key_gaps}
                />
              ) : null}
            </div>
          ) : null}
          <div>
            <p className="text-xs font-medium text-text-secondary mb-2">Score breakdown</p>
            <div className="space-y-1.5">
              {SCORE_DIMENSIONS.map(({ key, label }) => {
                const value = (app as unknown as Record<string, unknown>)[key] as number | null;
                const pct = value != null ? Math.min(value, 100) : 0;
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="w-[120px] shrink-0 text-[11px] text-text-tertiary truncate">{label}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-bg-muted overflow-hidden">
                      <div
                        className={cn('h-full rounded-full transition-all', scoreBgClass(value))}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span
                      className="w-6 text-right text-[11px] font-medium tabular-nums"
                      style={{ color: scoreColorHex(value) }}
                    >
                      {value != null ? Math.round(value) : '\u2014'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {expanded && <JobDetail app={app} />}

      <ApplyDrawer app={app} open={applyOpen} onClose={() => setApplyOpen(false)} />
    </Card>
  );
}
