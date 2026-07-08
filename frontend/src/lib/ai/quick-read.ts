/**
 * The rules-based quick read: 3 to 5 short lines built only from fields the
 * record actually states. This is the answer that ALWAYS renders in under a
 * second, on every device, before any fuller version is even mentioned.
 *
 * Honesty rules match board-card.ts, whose helpers do all the real work here:
 * no stated pay means no pay line, no verifiable date means no freshness
 * claim, quest needs come only from stated fields.
 */

import type { ApplicationResponse } from '@/types/application';
import {
  boardVertical,
  EVENT_WORDS,
  formatStatedPay,
  needsLine,
  parseReport,
  payUnitFor,
  questNeedsLine,
  questPay,
  shortDate,
} from '@/utils/board-card';
import { computeRequirementFit } from '@/utils/job-fit';
import { postedAgoLabel } from '@/utils/job-trust';

function capitalize(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

function payLine(app: ApplicationResponse): string | null {
  if (boardVertical(app) === 'career') {
    const pay = formatStatedPay(app.salary_min, app.salary_max);
    if (!pay) return null;
    const unit = payUnitFor(app);
    return `Pays ${pay}${unit ? ` ${unit}` : ''}.`;
  }
  const pay = questPay(app);
  if (!pay) return null;
  return `Pays ${pay.pay}${pay.payUnit ? ` ${pay.payUnit}` : ''}.`;
}

function placeLine(app: ApplicationResponse): string | null {
  if (app.is_remote) return 'Remote.';
  if (app.location) return `In ${app.location}.`;
  if ((app.quest as Record<string, unknown> | null | undefined)?.format === 'online') {
    return 'Online.';
  }
  return null;
}

function timingLine(app: ApplicationResponse): string | null {
  if (app.is_rolling) return 'Rolling sign-up.';
  const date = shortDate(app.event_start);
  if (!date) return null;
  const word = EVENT_WORDS[boardVertical(app)] ?? 'on';
  return `${capitalize(word)} ${date}.`;
}

function sourceLine(app: ApplicationResponse, sourceLabel?: string): string {
  const source = sourceLabel || app.source;
  const posted = postedAgoLabel(app.date_posted, app.date_confidence);
  return posted ? `From ${source}. ${posted}.` : `From ${source}.`;
}

/** The lines, in reading order. The source line is always present. */
export function quickReadLines(app: ApplicationResponse, sourceLabel?: string): string[] {
  const vertical = boardVertical(app);
  const lines: string[] = [];

  const pay = payLine(app);
  if (pay) lines.push(pay);

  const place = placeLine(app);
  if (place) lines.push(place);

  const needs =
    vertical === 'career'
      ? needsLine(computeRequirementFit(parseReport(app.evaluation_report_json)))
      : questNeedsLine(vertical, app.quest);
  if (needs) lines.push(`${needs}.`);

  const timing = timingLine(app);
  if (timing) lines.push(timing);

  lines.push(sourceLine(app, sourceLabel));
  return lines;
}

/** The quick read as one flowing paragraph for the result block. */
export function quickRead(app: ApplicationResponse, sourceLabel?: string): string {
  return quickReadLines(app, sourceLabel).join(' ');
}
