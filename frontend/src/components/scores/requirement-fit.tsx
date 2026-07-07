import { useState } from 'react';
import { Check, CircleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { computeRequirementFit } from '@/utils/job-fit';
import type { EvaluationReport } from '@/types/application';

/**
 * "Your fit" summary — the honest, at-a-glance answer to "should I bother?"
 *
 * Reads the backend's requirement-by-requirement evaluation and says, plainly,
 * how many of the job's stated requirements your resume covers, plus the
 * specific gaps to focus on. Framed as a guide, never as "beat the ATS."
 */
export function RequirementFit({ report }: { report: EvaluationReport | null }) {
  const [showAllCovered, setShowAllCovered] = useState(false);
  const fit = computeRequirementFit(report);
  if (!fit) return null;

  const LABEL_TONE: Record<string, string> = {
    'Strong fit': 'border-success/30 bg-success/10 text-success',
    'Good fit': 'border-success/30 bg-success/10 text-success',
    'Partial fit': 'border-warning/40 bg-warning/10 text-warning',
    'Stretch': 'border-warning/40 bg-warning/10 text-warning',
  };
  const barTone = fit.ratio >= 0.6 ? 'bg-success' : 'bg-warning';

  const coveredShown = showAllCovered ? fit.covered : fit.covered.slice(0, 6);
  const coveredHidden = fit.covered.length - coveredShown.length;

  return (
    <div className="rounded-lg border border-border-default bg-bg-card p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-text-primary">Your fit</span>
          <span className="text-xs text-text-tertiary">
            You clearly cover <span className="font-semibold text-text-primary tabular-nums">{fit.strong}</span> of{' '}
            <span className="font-semibold text-text-primary tabular-nums">{fit.total}</span> requirements
            {fit.partial > 0 && <span className="text-text-muted"> · {fit.partial} partial</span>}
          </span>
        </div>
        <span
          className={cn(
            'inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium',
            LABEL_TONE[fit.label],
          )}
        >
          {fit.label}
        </span>
      </div>

      {/* Coverage bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-muted">
        <div className={cn('h-full rounded-full transition-all', barTone)} style={{ width: `${Math.round(fit.ratio * 100)}%` }} />
      </div>

      {/* Covered requirements */}
      {coveredShown.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {coveredShown.map((r, i) => (
            <span
              key={i}
              title={r.evidence || undefined}
              className="inline-flex items-center gap-1 rounded-md border border-success/25 bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success"
            >
              <Check className="h-3 w-3 shrink-0" />
              <span className="truncate max-w-[220px]">{r.requirement}</span>
            </span>
          ))}
          {coveredHidden > 0 && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setShowAllCovered(true); }}
              className="text-[11px] text-text-tertiary hover:text-text-secondary underline-offset-2 hover:underline"
            >
              +{coveredHidden} more
            </button>
          )}
        </div>
      )}

      {/* Gaps to focus on */}
      {fit.gaps.length > 0 && (
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-text-muted">Focus your pitch here</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {fit.gaps.map((r, i) => (
              <span
                key={i}
                title={r.mitigation || undefined}
                className="inline-flex items-center gap-1 rounded-md border border-warning/40 bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning"
              >
                <CircleAlert className="h-3 w-3 shrink-0" />
                <span className="truncate max-w-[220px]">{r.requirement}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-text-muted">
        Measured against this job's stated requirements versus your resume. A guide for where to focus, not a pass/fail gate.
      </p>
    </div>
  );
}
