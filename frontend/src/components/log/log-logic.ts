/**
 * Pure logic for Your log (/log), pinned by log-logic.test.ts.
 *
 * The log is one list built from two lanes of the applications table:
 * - personal quests (vertical 'personal'): everything the user wrote in
 *   the composer belongs in the log, whatever its status
 * - board rows that entered the log by action: clipped, applied, shelved,
 *   or done; plain 'found' board rows never appear here
 *
 * Honesty rules: the paid total counts only figures the user typed when
 * marking a quest done (quest.paid_out), never a number the source stated
 * or the app inferred. Every date is a real row timestamp.
 */

import type { ApplicationFilters, ApplicationResponse } from '@/types/application';
import { parseAmount, shortDate } from '@/utils/board-card';
import { ALL_VERTICALS } from '@/utils/board-verticals';

/** Board rows join the log only through one of these statuses. */
export const LOG_BOARD_STATUSES =
  'clipped,reviewed,applying,applied,interviewing,offer,shelved,attended,paid_out';

/* The two log queries. Object identity does not matter for the cache key
   (TanStack hashes structurally), but sharing the definitions keeps every
   consumer on the same keys. */
export function personalLogFilters(profile?: string): ApplicationFilters {
  return {
    vertical: 'personal',
    sort_by: 'updated_at',
    sort_order: 'desc',
    page: 1,
    page_size: 100,
    profile,
  };
}

export function boardLogFilters(profile?: string): ApplicationFilters {
  return {
    // every registry lane: a clipped bank bonus belongs in the log too
    vertical: ALL_VERTICALS,
    status: LOG_BOARD_STATUSES,
    sort_by: 'updated_at',
    sort_order: 'desc',
    page: 1,
    page_size: 100,
    profile,
  };
}

const DONE_STATUSES = new Set(['attended', 'paid_out']);
const APPLIED_STATUSES = new Set(['applied', 'interviewing', 'offer']);

export function isPersonal(app: Pick<ApplicationResponse, 'vertical'>): boolean {
  return app.vertical === 'personal';
}

export function isApplied(app: Pick<ApplicationResponse, 'status'>): boolean {
  return APPLIED_STATUSES.has(app.status);
}

export function isDone(app: Pick<ApplicationResponse, 'status'>): boolean {
  return DONE_STATUSES.has(app.status);
}

export function isShelved(app: Pick<ApplicationResponse, 'status'>): boolean {
  return app.status === 'shelved';
}

/** When the row last moved: the timestamp the log sorts and dates by. */
function touchedAt(app: ApplicationResponse): number {
  const stamp = app.updated_at ?? app.date_found ?? app.created_at;
  const t = stamp ? Date.parse(stamp) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

export function logDate(app: ApplicationResponse): string | null {
  return (
    shortDate(app.updated_at) ?? shortDate(app.date_found) ?? shortDate(app.created_at)
  );
}

export interface LogSplit {
  /** Open and shelved cards, newest movement first. */
  active: ApplicationResponse[];
  /** Done rows for the dated ledger, newest first. */
  done: ApplicationResponse[];
}

/** Merge the two lanes into the one log: cards up top, the Done ledger below. */
export function splitLog(
  personal: ApplicationResponse[],
  board: ApplicationResponse[],
): LogSplit {
  const all = [...personal, ...board].sort((a, b) => touchedAt(b) - touchedAt(a));
  return {
    active: all.filter((app) => !isDone(app)),
    done: all.filter((app) => isDone(app)),
  };
}

/**
 * The paid figure the user typed when marking the quest done. Only a real
 * positive number counts; anything else (absent, zero, a string, a scraped
 * salary field) is "nothing landed yet".
 */
export function paidOut(app: Pick<ApplicationResponse, 'quest'>): number | null {
  const v = app.quest?.paid_out;
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

/** Sum of user-entered paid figures among done rows touched in `year`. */
export function paidTotal(done: ApplicationResponse[], year: number): number {
  let total = 0;
  for (const app of done) {
    const amount = paidOut(app);
    if (amount === null) continue;
    const t = touchedAt(app);
    if (t > 0 && new Date(t).getFullYear() === year) total += amount;
  }
  return total;
}

/** "$45" or "125" or "1,500" from the done input; null when empty or junk. */
export function parsePaidInput(raw: string): number | null {
  if (!raw.trim()) return null;
  const n = parseAmount(raw);
  return n !== null && n > 0 ? n : null;
}

/** quest_json for a done-with-pay edit: existing facts kept, figure added. */
export function withPaidOut(app: Pick<ApplicationResponse, 'quest'>, amount: number): string {
  return JSON.stringify({ ...(app.quest ?? {}), paid_out: amount });
}

/** Reopening a shelved row: personal quests go back to open, clips to clipped. */
export function reopenStatus(app: Pick<ApplicationResponse, 'vertical'>): string {
  return isPersonal(app) ? 'found' : 'clipped';
}

/**
 * "Applied Jun 30. A short follow-up is fair game after Jul 7. One note is
 * plenty." Only when a real applied date exists; nothing is guessed.
 */
export function followUpLine(app: ApplicationResponse): string | null {
  if (!isApplied(app) || !app.date_applied) return null;
  const appliedT = Date.parse(app.date_applied);
  if (Number.isNaN(appliedT)) return null;
  const applied = shortDate(app.date_applied);
  const after = shortDate(new Date(appliedT + 7 * 24 * 60 * 60 * 1000).toISOString());
  if (!applied || !after) return null;
  return `Applied ${applied}. A short follow-up is fair game after ${after}. One note is plenty.`;
}

/**
 * The optional email row appears only once the log holds something worth
 * keeping: any personal quest, or two or more board rows.
 */
export function hasLogValue(split: LogSplit): boolean {
  const all = [...split.active, ...split.done];
  if (all.some(isPersonal)) return true;
  return all.filter((app) => !isPersonal(app)).length >= 2;
}

/* ── the email row's three states, stored in this browser ── */

export type SignupState = 'row' | 'email' | 'sent' | 'dismissed';

const EMAIL_KEY = 'questboard:log-email';
const DISMISSED_KEY = 'questboard:log-email-dismissed';

/** All storage reads and writes stay inside try/catch, as entry.ts does. */
export function readSignupState(storage: Pick<Storage, 'getItem'>): SignupState {
  try {
    if (storage.getItem(EMAIL_KEY)) return 'sent';
    if (storage.getItem(DISMISSED_KEY)) return 'dismissed';
  } catch {
    /* storage unavailable: show the row, saving will no-op */
  }
  return 'row';
}

export function saveSignupEmail(storage: Pick<Storage, 'setItem'>, email: string): boolean {
  const trimmed = email.trim();
  if (!isPlausibleEmail(trimmed)) return false;
  try {
    storage.setItem(EMAIL_KEY, trimmed);
  } catch {
    /* storage unavailable; the UI still moves on honestly */
  }
  return true;
}

export function dismissSignup(storage: Pick<Storage, 'setItem'>): void {
  try {
    storage.setItem(DISMISSED_KEY, '1');
  } catch {
    /* storage unavailable */
  }
}

export function isPlausibleEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
