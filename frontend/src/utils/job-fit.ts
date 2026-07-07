/**
 * Honest resume-fit math (Phase 2).
 *
 * Turns the backend's requirement-by-requirement evaluation into an
 * at-a-glance "you cover N of M requirements" read. The framing is
 * deliberately a guide, not a gate: recruiters say the auto-reject "ATS
 * robot" is a myth, and job seekers resent fear-selling, so we report honest
 * overlap and where to focus, never "beat the filter."
 */

import type { EvaluationReport, RequirementMatch } from '@/types/application';

export interface RequirementFit {
  total: number;
  strong: number;
  partial: number;
  missing: number;
  /** Weighted coverage 0..1 (partial counts half). */
  ratio: number;
  /** Human label for the fit level. */
  label: 'Strong fit' | 'Good fit' | 'Partial fit' | 'Stretch';
  covered: RequirementMatch[];   // strength === 'strong'
  partials: RequirementMatch[];  // strength === 'partial'
  gaps: RequirementMatch[];      // strength === 'missing'
}

export function computeRequirementFit(
  report: EvaluationReport | null | undefined,
): RequirementFit | null {
  const reqs = report?.requirements;
  if (!reqs || reqs.length === 0) return null;

  const covered = reqs.filter((r) => r.strength === 'strong');
  const partials = reqs.filter((r) => r.strength === 'partial');
  const gaps = reqs.filter((r) => r.strength === 'missing');
  const total = reqs.length;
  const ratio = (covered.length + partials.length * 0.5) / total;

  const label: RequirementFit['label'] =
    ratio >= 0.8 ? 'Strong fit'
      : ratio >= 0.6 ? 'Good fit'
        : ratio >= 0.4 ? 'Partial fit'
          : 'Stretch';

  return {
    total,
    strong: covered.length,
    partial: partials.length,
    missing: gaps.length,
    ratio,
    label,
    covered,
    partials,
    gaps,
  };
}
