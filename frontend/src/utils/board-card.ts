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
 * - quest rows (vertical camera/study/lens/party) never claim a resume need;
 *   their needs line is assembled only from fields the source stated
 */

import { kindForVertical } from '@questboard/kinds';
import type { ApplicationResponse, EvaluationReport } from '@/types/application';
import { computeRequirementFit, type RequirementFit } from '@/utils/job-fit';
import { postedAgoLabel } from '@/utils/job-trust';

/** 'career' or any registry-known quest vertical (kind ids and legacy names). */
export type BoardVertical = string;

/** The row's vertical, from the kinds registry, never a hand list here:
    'career' keeps the resume-fit card shape, every other registry-known
    vertical gets the quest shape (quest pay grammar, no resume claims),
    and anything unknown falls back to career. */
export function boardVertical(app: Pick<ApplicationResponse, 'vertical'>): BoardVertical {
  const v = app.vertical || 'career';
  if (v === 'career') return 'career';
  return kindForVertical(v) ? v : 'career';
}

export interface BoardCardModel {
  id: number;
  vertical: BoardVertical;
  title: string;
  href?: string;
  meta: string;
  needs: string;
  firstQuest?: boolean;
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

export function payUnitFor(app: ApplicationResponse): string {
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

type Quest = Record<string, unknown> | null | undefined;

function questNum(quest: Quest, key: string): number | null {
  const v = quest?.[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function questStr(quest: Quest, key: string): string {
  const v = quest?.[key];
  return typeof v === 'string' ? v : '';
}

function ageLabel(quest: Quest): string {
  const min = questNum(quest, 'age_min');
  const max = questNum(quest, 'age_max');
  if (min !== null && max !== null) return `ages ${min} to ${max}`;
  if (min !== null) return `ages ${min} and up`;
  if (max !== null) return `ages up to ${max}`;
  return '';
}

/**
 * Needs line for a quest row, from stated fields only; '' when the source
 * stated nothing. Study rows lead with "screener only": research and trial
 * sources gate on a screener and demographics, never a resume.
 */
export function questNeedsLine(vertical: BoardVertical, quest: Quest): string {
  if (!quest) return '';
  const parts: string[] = [];
  if (vertical === 'study') parts.push('screener only');
  if (quest.healthy_volunteers === true) parts.push('healthy volunteers');
  const sex = questStr(quest, 'sex').toLowerCase();
  if (sex === 'female') parts.push('women only');
  if (sex === 'male') parts.push('men only');
  const ages = ageLabel(quest);
  if (ages) parts.push(ages);
  const union = questStr(quest, 'union');
  if (union) parts.push(union);
  const tickets = questNum(quest, 'max_tickets');
  if (tickets !== null) parts.push(`up to ${tickets} tickets`);
  return parts.length ? `Needs: ${parts.join(', ')}` : '';
}

/** "taping Jul 14" for camera, "session Jul 14" for studies. */
export const EVENT_WORDS: Partial<Record<BoardVertical, string>> = {
  camera: 'taping',
  study: 'session',
};

/** "{source}, posted 2 days ago, taping Jul 14, Atlanta" or "rolling sign-up". */
export function questMeta(app: ApplicationResponse, sourceLabel?: string): string {
  const posted = postedAgoLabel(app.date_posted, app.date_confidence);
  let timing = '';
  if (app.is_rolling) {
    timing = 'rolling sign-up';
  } else {
    const date = shortDate(app.event_start);
    if (date) timing = `${EVENT_WORDS[boardVertical(app)] ?? 'on'} ${date}`;
  }
  const place = app.is_remote
    ? 'remote'
    : app.location || (questStr(app.quest, 'format') === 'online' ? 'online' : '');
  return [sourceLabel || app.source, posted ? posted.toLowerCase() : '', timing, place]
    .filter(Boolean)
    .join(', ');
}

const QUEST_PERIOD_UNITS: Record<string, string> = {
  session: 'a session',
  hourly: '/hr',
  daily: 'a day',
  weekly: 'a week',
  monthly: 'a month',
  yearly: 'a year',
};

function fmtQuestAmount(n: number): string {
  return n.toLocaleString('en-US');
}

/**
 * Quest pay stays the raw stated session-scale numbers: "$125" + "max" for an
 * up-to chip (the mock's grammar), "$100–125" + "a session" for a range,
 * "$500" + "/12 hr" for a casting day rate with stated hours.
 */
export function questPay(app: ApplicationResponse): { pay: string; payUnit: string } | null {
  const min = app.salary_min;
  const max = app.salary_max;
  if (min == null && max == null) return null;
  const period = (app.salary_period || '').toLowerCase();
  let unit = QUEST_PERIOD_UNITS[period] || '';
  const hours = questNum(app.quest, 'session_hours');
  if (period === 'daily' && hours !== null) unit = `/${hours} hr`;

  let pay: string;
  if (min != null && max != null && min !== max) {
    pay = `$${fmtQuestAmount(min)}–${fmtQuestAmount(max)}`;
  } else if (min != null) {
    pay = max == null ? `$${fmtQuestAmount(min)}+` : `$${fmtQuestAmount(min)}`;
  } else {
    /* max only: an "up to" figure; "max" says so without inventing a floor */
    pay = `$${fmtQuestAmount(max as number)}`;
    unit = 'max';
  }
  if (app.salary_source === 'parsed_from_description') {
    unit = unit ? `${unit}, estimated from description` : 'estimated from description';
  }
  return { pay, payUnit: unit };
}

const normalizeName = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

/** Quest title; the company is dropped when it just restates the source
    or when the title already names it (speak rows: "Speak at X" + X). */
function questTitle(app: ApplicationResponse, sourceLabel?: string): string {
  const company = (app.company || '').trim();
  if (!company) return app.job_title;
  const norm = normalizeName(company);
  if (norm === normalizeName(app.source) || norm === normalizeName(sourceLabel || '')) {
    return app.job_title;
  }
  if (norm && normalizeName(app.job_title).includes(norm)) {
    return app.job_title;
  }
  return `${app.job_title}, ${company}`;
}

function stampStatus(card: BoardCardModel, app: ApplicationResponse): void {
  if (APPLIED_STATUSES.has(app.status)) {
    const date = shortDate(app.date_applied);
    card.applied = date ? `Applied, ${date}` : 'Applied';
  } else if (CLIPPED_STATUSES.has(app.status)) {
    card.clippedDate =
      shortDate(app.updated_at) ?? shortDate(app.date_found) ?? 'earlier';
  }
}

function toQuestBoardCard(
  app: ApplicationResponse,
  vertical: BoardVertical,
  sourceLabel?: string,
): BoardCardModel {
  const card: BoardCardModel = {
    id: app.id,
    vertical,
    title: questTitle(app, sourceLabel),
    href: app.job_url || undefined,
    meta: questMeta(app, sourceLabel),
    needs: questNeedsLine(vertical, app.quest),
    fit: null,
    report: null,
  };
  if (app.first_quest_ok) card.firstQuest = true;
  const pay = questPay(app);
  if (pay) {
    card.pay = pay.pay;
    card.payUnit = pay.payUnit;
  }
  stampStatus(card, app);
  return card;
}

export function toBoardCard(app: ApplicationResponse, sourceLabel?: string): BoardCardModel {
  const vertical = boardVertical(app);
  if (vertical !== 'career') return toQuestBoardCard(app, vertical, sourceLabel);

  const report = parseReport(app.evaluation_report_json);
  const fit = computeRequirementFit(report);

  const card: BoardCardModel = {
    id: app.id,
    vertical,
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

  stampStatus(card, app);
  return card;
}
