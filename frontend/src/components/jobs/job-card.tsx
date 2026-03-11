import { useState } from 'react';
import { ExternalLink, ChevronDown, MapPin, Send, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CompanyAvatar } from '@/components/shared/company-avatar';
import { ScoreCircle } from '@/components/scores/score-circle';
import { RecommendationBadge } from '@/components/badges/recommendation-badge';
import { CompanyTypeBadge } from '@/components/badges/company-type-badge';
import { WorkTypeBadge } from '@/components/badges/work-type-badge';
import { SalaryBadge } from '@/components/badges/salary-badge';
import { FundingBadge } from '@/components/badges/funding-badge';
import { JobDetail } from './job-detail';
import { ApplyDrawer } from './apply-drawer';
import { truncateDescription, formatDate } from '@/utils/format';
import { cn } from '@/lib/utils';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
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

interface JobCardProps {
  app: ApplicationResponse;
  sourceLabels?: Record<string, string>;
}

export function JobCard({ app, sourceLabels }: JobCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const labels = sourceLabels;
  const isApplied = app.status === 'applied';

  const borderColor = REC_BORDER_COLORS[app.recommendation] || REC_BORDER_COLORS.SKIP;
  const recency = getRecencyLabel(app.date_found);

  return (
    <Card
      className={cn(
        'overflow-hidden border-l-[3px] transition-all duration-150',
        !expanded && 'hover:shadow-md hover:-translate-y-[1px]',
        expanded && 'shadow-md',
      )}
      style={{ borderLeftColor: borderColor }}
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={`${app.job_title} at ${app.company}, ${expanded ? 'collapse' : 'expand'} details`}
        className="flex items-start gap-4 p-5 w-full text-left cursor-pointer select-none focus-ring rounded-lg"
        onClick={() => setExpanded(!expanded)}
      >
        <CompanyAvatar company={app.company} />

        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-text-primary leading-snug">{app.job_title}</h3>
              <p className="text-sm text-text-secondary mt-0.5">
                {app.company}
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
            <div className="flex items-center gap-2 shrink-0">
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

          {/* Score rationale */}
          {app.score_reasoning && (
            <p className="mt-1.5 text-xs text-text-muted italic line-clamp-1">
              {app.score_reasoning.split(/[.!]/)[0]?.trim() || app.score_reasoning}
            </p>
          )}

          {/* Badges */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            <RecommendationBadge recommendation={app.recommendation} />
            <CompanyTypeBadge companyType={app.company_type} />
            <WorkTypeBadge workType={app.work_type} isRemote={app.is_remote} />
            <SalaryBadge min={app.salary_min} max={app.salary_max} />
            <FundingBadge app={app} />
          </div>

          {/* Meta row */}
          <div className="mt-3 flex items-center gap-3 text-xs text-text-muted">
            {app.source && (
              <span className="inline-flex items-center rounded-md bg-bg-subtle border border-border-default px-1.5 py-0.5 text-[11px] font-medium text-text-tertiary">
                {resolveSourceLabel(app.source, labels)}
              </span>
            )}
            {recency && <span>{recency}</span>}
            {app.date_found && !recency && <span>{formatDate(app.date_found, 'relative')}</span>}
            {app.date_found && recency && <span>{formatDate(app.date_found, 'relative')}</span>}
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
                  View posting
                </a>
              )
            )}
            <span className="ml-auto" onClick={(e) => e.stopPropagation()}>
              {isApplied ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">
                  <CheckCircle2 className="h-3 w-3" />
                  Applied
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    setApplyOpen(true);
                  }}
                  className="text-[11px] gap-1"
                >
                  <Send className="h-3 w-3" />
                  Apply
                </Button>
              )}
            </span>
          </div>
        </div>
      </button>

      {expanded && <JobDetail app={app} />}

      <ApplyDrawer app={app} open={applyOpen} onClose={() => setApplyOpen(false)} />
    </Card>
  );
}
