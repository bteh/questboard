import { AlertTriangle, CheckCircle2, CircleAlert, Compass, Quote, Target, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { EvaluationReport, RequirementMatch } from '@/types/application';

/**
 * Renders the structured evaluation report produced by the backend for a
 * STRONG_APPLY job. Inspired by career-ops's 6-block structure: archetype
 * + TL;DR at the top, a requirement→resume-line mapping table in the middle,
 * prioritized gaps, recommended framing, and red flags.
 *
 * The requirement table is the load-bearing part of this component: for
 * each JD requirement we show a strength badge and the exact resume quote
 * that proves it. This is the "show your work" reasoning a hiring manager
 * would recognize — not a 0-100 number.
 */
interface EvaluationReportViewProps {
  report: EvaluationReport;
}

const STRENGTH_STYLES: Record<RequirementMatch['strength'], { label: string; className: string; icon: typeof CheckCircle2 }> = {
  strong: {
    label: 'Strong',
    className: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300',
    icon: CheckCircle2,
  },
  partial: {
    label: 'Partial',
    className: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300',
    icon: CircleAlert,
  },
  missing: {
    label: 'Missing',
    className: 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300',
    icon: XCircle,
  },
};

export function EvaluationReportView({ report }: EvaluationReportViewProps) {
  const hasRequirements = report.requirements && report.requirements.length > 0;
  const hasTopGaps = report.top_gaps && report.top_gaps.length > 0;
  const hasRedFlags = report.red_flags && report.red_flags.length > 0;
  const hasFraming = !!report.recommended_framing?.trim();

  return (
    <div className="space-y-5">
      {/* Archetype + TL;DR */}
      {(report.archetype || report.tldr) && (
        <div className="rounded-xl border border-brand/20 bg-brand-light/20 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/10">
              <Compass className="h-4 w-4 text-brand" />
            </div>
            <div className="min-w-0 flex-1">
              {report.archetype && (
                <div className="mb-1">
                  <span className="inline-flex items-center rounded-full border border-brand/30 bg-bg-card px-2.5 py-0.5 text-[11px] font-medium text-brand">
                    {report.archetype}
                  </span>
                </div>
              )}
              {report.tldr && (
                <p className="text-sm leading-relaxed text-text-primary">{report.tldr}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Requirement → resume line mapping */}
      {hasRequirements && (
        <section>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
            Requirements vs. your resume
          </h4>
          <div className="space-y-2">
            {report.requirements.map((req, idx) => (
              <RequirementRow key={`${idx}-${req.requirement.slice(0, 32)}`} match={req} />
            ))}
          </div>
        </section>
      )}

      {/* Top gaps */}
      {hasTopGaps && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
            <Target className="h-3 w-3" />
            Most important gaps to address
          </h4>
          <ul className="space-y-1.5 rounded-lg border border-border-default bg-bg-card p-3">
            {report.top_gaps.map((gap, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Recommended framing */}
      {hasFraming && (
        <section>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
            How to position yourself
          </h4>
          <div className="rounded-lg border border-border-default bg-bg-card p-3">
            <p className="text-sm leading-relaxed text-text-secondary">{report.recommended_framing}</p>
          </div>
        </section>
      )}

      {/* Red flags */}
      {hasRedFlags && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
            <AlertTriangle className="h-3 w-3" />
            Red flags to weigh before applying
          </h4>
          <ul className="space-y-1.5 rounded-lg border border-rose-200/60 bg-rose-50/50 p-3 dark:border-rose-900/40 dark:bg-rose-950/20">
            {report.red_flags.map((flag, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-rose-500" />
                <span>{flag}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function RequirementRow({ match }: { match: RequirementMatch }) {
  const strength = STRENGTH_STYLES[match.strength] ?? STRENGTH_STYLES.missing;
  const StrengthIcon = strength.icon;
  return (
    <div className="rounded-lg border border-border-default bg-bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 text-sm font-medium text-text-primary leading-snug">
          {match.requirement}
        </p>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
            strength.className,
          )}
        >
          <StrengthIcon className="h-3 w-3" />
          {strength.label}
        </span>
      </div>

      {match.evidence && (
        <div className="mt-2 flex items-start gap-2 rounded-md bg-bg-subtle/60 px-2.5 py-2">
          <Quote className="mt-0.5 h-3 w-3 shrink-0 text-text-muted" />
          <p className="text-[12px] italic leading-relaxed text-text-secondary">
            {match.evidence}
          </p>
        </div>
      )}

      {match.mitigation && (
        <p className="mt-2 text-[12px] leading-relaxed text-text-tertiary">
          <span className="font-medium text-text-secondary">How to address:</span> {match.mitigation}
        </p>
      )}
    </div>
  );
}
