/**
 * Maps a real ApplicationResponse onto the quest-board card grammar.
 *
 * Honesty rules, enforced here and pinned by board-card.test.ts:
 * - the posted label comes from job-trust postedAgoLabel, so a posting with
 *   no verifiable date says nothing about freshness at all
 * - the needs line reports requirement coverage only when a real evaluation
 *   report exists; there is no invented percentage or fit score
 * - pay renders only when the record states pay, always the raw stated
 *   numbers, and parsed-from-description pay is marked as estimated
 *   (same standard as job-card.tsx / salary-badge.tsx)
 */

import type { ApplicationResponse, EvaluationReport } from '@/types/application';
import { computeRequirementFit, type RequirementFit } from '@/utils/job-fit';
import { postedAgoLabel } from '@/utils/job-trust';

export interface BoardCardModel {
  id: number;
  title: string;
  href?: string;
  meta: string;
  needs: string;
  /** Parsed requirement fit, null when no evaluation report exists. */
  fit: RequirementFit | null;
  /** The full report backing the fit, for the requirement ledger sheet. */
  report: EvaluationReport | null;
  pay?: string;
  payUnit?: string;
  /** e.g. "Applied, Jun 30"; set for statuses that mean an application went out. */
  applied?: string;
  /** Short date once the row is clipped (status saved/shortlisted). */
  clippedDate?: string;
}

/** Statuses that mean an application actually went out. */
const APPLIED_STATUSES = new Set(['applied', 'interviewing', 'offer']);
/** The real saved/shortlisted status the board writes on Clip. */
export const CLIP_STATUS = 'clipped';
/** 'reviewed' stays recognized: rows clipped before 'clipped' existed keep rendering as clipped. */
const CLIPPED_STATUSES = new Set([CLIP_STATUS, 'reviewed', 'applying']);

/** "150k" -> 150000, "$1,500" -> 1500. Null when unparseable. */
export function parseAmount(raw: string): number | null {
  const s = String(raw).toLowerCase().replace(/[$,\s]/g, '');
  if (!s) return null;
  const thousands = /k$/.test(s);
  const n = parseFloat(s.replace(/k$/, ''));
  if (Number.isNaN(n)) return null;
  return thousands ? n * 1000 : n;
}

export function parseReport(json: string | null | undefined): EvaluationReport | null {
  if (!json) return null;
  try {
    const parsed = JSON.parse(json) as EvaluationReport;
    return parsed && Array.isArray(parsed.requirements) ? parsed : null;
  } catch {
    return null;
  }
}

/** Annualized bounds for filtering; falls back to the raw stated numbers. */
export function annualBounds(app: Pick<
  ApplicationResponse,
  'salary_min' | 'salary_max' | 'salary_min_annualized' | 'salary_max_annualized'
>): { lo: number | null; hi: number | null } {
  return {
    lo: app.salary_min_annualized ?? app.salary_min ?? null,
    hi: app.salary_max_annualized ?? app.salary_max ?? null,
  };
}

/**
 * True when the row's stated pay midpoint sits at or under the ceiling.
 * Rows with no stated pay stay in, mirroring the API's salary_min floor:
 * "no pay stated" is not "pays above your ceiling".
 */
export function withinPayCeiling(app: ApplicationResponse, ceiling: number | null): boolean {
  if (ceiling === null) return true;
  const { lo, hi } = annualBounds(app);
  if (lo === null && hi === null) return true;
  if (lo !== null && hi !== null) return (lo + hi) / 2 <= ceiling;
  return (hi ?? lo ?? 0) <= ceiling;
}

function fmtBound(n: number): string {
  return n >= 1000 ? `${Math.round(n / 1000)}` : `${n}`;
}

/** "$160–190k", "$58–72", "$170k+", "up to $95k". Empty when no pay stated. */
export function formatStatedPay(min: number | null, max: number | null): string {
  const k = (n: number) => n >= 1000;
  if (min != null && max != null) {
    if (k(min) && k(max)) return `$${fmtBound(min)}–${fmtBound(max)}k`;
    return `$${min}–${max}`;
  }
  if (min != null) return k(min) ? `$${fmtBound(min)}k+` : `$${min}+`;
  if (max != null) return k(max) ? `up to $${fmtBound(max)}k` : `up to $${max}`;
  return '';
}

const PERIOD_UNITS: Record<string, string> = {
  yearly: 'a year',
  monthly: 'a month',
  weekly: 'a week',
  daily: 'a day',
  hourly: '/hr',
};

function payUnitFor(app: ApplicationResponse): string {
  const unit = PERIOD_UNITS[(app.salary_period || '').toLowerCase()] || '';
  // Match the existing salary_source standard: only parsed-from-description
  // pay gets the estimated marker; reported or unknown provenance stays bare.
  if (app.salary_source === 'parsed_from_description') {
    return unit ? `${unit}, estimated from description` : 'estimated from description';
  }
  return unit;
}

export function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** "{source}, posted 3 days ago, remote". Skips whatever the record can't back. */
export function boardMeta(app: ApplicationResponse, sourceLabel?: string): string {
  const posted = postedAgoLabel(app.date_posted, app.date_confidence);
  const place = app.is_remote ? 'remote' : app.location || '';
  return [sourceLabel || app.source, posted ? posted.toLowerCase() : '', place]
    .filter(Boolean)
    .join(', ');
}

export function needsLine(fit: RequirementFit | null): string {
  if (!fit) return 'Needs: resume';
  return `Needs: resume, covers ${fit.strong} of ${fit.total} requirements`;
}

export function toBoardCard(app: ApplicationResponse, sourceLabel?: string): BoardCardModel {
  const report = parseReport(app.evaluation_report_json);
  const fit = computeRequirementFit(report);

  const card: BoardCardModel = {
    id: app.id,
    title: `${app.job_title}, ${app.company}`,
    href: app.job_url || undefined,
    meta: boardMeta(app, sourceLabel),
    needs: needsLine(fit),
    fit,
    report,
  };

  const pay = formatStatedPay(app.salary_min, app.salary_max);
  if (pay) {
    card.pay = pay;
    card.payUnit = payUnitFor(app);
  }

  if (APPLIED_STATUSES.has(app.status)) {
    const date = shortDate(app.date_applied);
    card.applied = date ? `Applied, ${date}` : 'Applied';
  } else if (CLIPPED_STATUSES.has(app.status)) {
    card.clippedDate =
      shortDate(app.updated_at) ?? shortDate(app.date_found) ?? 'earlier';
  }

  return card;
}
