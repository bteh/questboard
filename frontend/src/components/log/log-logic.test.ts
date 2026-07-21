import { describe, expect, it } from 'vitest';
import {
  boardLogFilters,
  dismissSignup,
  followUpLine,
  hasLogValue,
  isPlausibleEmail,
  paidOut,
  paidTotal,
  parsePaidInput,
  personalLogFilters,
  readSignupState,
  reopenStatus,
  rowActions,
  saveSignupEmail,
  splitLog,
  withPaidOut,
} from './log-logic';
import { LOG_BOARD_STATUSES } from './log-logic';
import { ALL_VERTICALS, VERTICAL_KEYS, verticalParams } from '@/utils/board-verticals';
import type { ApplicationResponse } from '@/types/application';

/* Pipeline-set statuses stay visible: 'booked' (booking flow) and 'expired'
   (expiry pipeline) are written without the user picking them, so the log's
   board filter must include them or those rows silently vanish. */
describe('log board status filter', () => {
  it('includes the pipeline-set statuses booked and expired', () => {
    const statuses = LOG_BOARD_STATUSES.split(',');
    expect(statuses).toContain('booked');
    expect(statuses).toContain('expired');
  });
});

function app(over: Partial<ApplicationResponse>): ApplicationResponse {
  return {
    id: 1,
    job_title: 'Quest',
    company: '',
    location: '',
    job_url: '',
    source: 'user',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
    salary_currency: '',
    salary_period: '',
    salary_min_annualized: null,
    salary_max_annualized: null,
    status: 'found',
    vertical: 'personal',
    ...over,
  } as ApplicationResponse;
}

describe('splitLog', () => {
  it('interleaves personal and board rows newest movement first', () => {
    const personal = [
      app({ id: 1, updated_at: '2026-07-06T10:00:00Z' }),
      app({ id: 2, updated_at: '2026-07-01T10:00:00Z' }),
    ];
    const board = [
      app({ id: 3, vertical: 'study', status: 'clipped', updated_at: '2026-07-07T10:00:00Z' }),
      app({ id: 4, vertical: 'career', status: 'applied', updated_at: '2026-07-03T10:00:00Z' }),
    ];
    const { active } = splitLog(personal, board);
    expect(active.map((a) => a.id)).toEqual([3, 1, 4, 2]);
  });

  it('routes done rows to the ledger and keeps the rest as cards', () => {
    const personal = [
      app({ id: 1, status: 'paid_out', updated_at: '2026-07-05T10:00:00Z' }),
      app({ id: 2, status: 'shelved', updated_at: '2026-07-04T10:00:00Z' }),
      app({ id: 3, status: 'found', updated_at: '2026-07-03T10:00:00Z' }),
    ];
    const board = [
      app({ id: 4, vertical: 'study', status: 'attended', updated_at: '2026-07-06T10:00:00Z' }),
    ];
    const { active, done } = splitLog(personal, board);
    expect(active.map((a) => a.id)).toEqual([2, 3]);
    expect(done.map((a) => a.id)).toEqual([4, 1]);
  });
});

describe('paid figures', () => {
  it('counts only a real user-entered number', () => {
    expect(paidOut(app({ quest: { paid_out: 45 } }))).toBe(45);
    expect(paidOut(app({ quest: { paid_out: 0 } }))).toBeNull();
    expect(paidOut(app({ quest: { paid_out: '45' } }))).toBeNull();
    expect(paidOut(app({ quest: {} }))).toBeNull();
    expect(paidOut(app({ quest: null }))).toBeNull();
    expect(paidOut(app({}))).toBeNull();
    /* stated pay on the row is NOT a paid-out figure */
    expect(paidOut(app({ salary_min: 500, quest: null }))).toBeNull();
  });

  it('totals only done rows with real figures inside the year', () => {
    const done = [
      app({ id: 1, status: 'paid_out', quest: { paid_out: 45 }, updated_at: '2026-07-03T10:00:00Z' }),
      app({ id: 2, status: 'paid_out', quest: { paid_out: 125 }, updated_at: '2026-06-28T10:00:00Z' }),
      /* done without a figure: in the ledger, not in the total */
      app({ id: 3, status: 'attended', updated_at: '2026-03-04T10:00:00Z' }),
      /* paid last year: not this year's line */
      app({ id: 4, status: 'paid_out', quest: { paid_out: 999 }, updated_at: '2025-12-30T10:00:00Z' }),
    ];
    expect(paidTotal(done, 2026)).toBe(170);
    expect(paidTotal([], 2026)).toBe(0);
  });

  it('parses the done input and rejects junk', () => {
    expect(parsePaidInput('45')).toBe(45);
    expect(parsePaidInput('$1,500')).toBe(1500);
    expect(parsePaidInput('')).toBeNull();
    expect(parsePaidInput('  ')).toBeNull();
    expect(parsePaidInput('soon')).toBeNull();
    expect(parsePaidInput('0')).toBeNull();
  });

  it('merges the figure into existing quest facts', () => {
    expect(JSON.parse(withPaidOut(app({ quest: { format: 'online' } }), 45))).toEqual({
      format: 'online',
      paid_out: 45,
    });
    expect(JSON.parse(withPaidOut(app({}), 45))).toEqual({ paid_out: 45 });
  });
});

describe('rowActions', () => {
  it('offers Done, Shelve and Remove on a clipped or reviewed row', () => {
    expect(rowActions(app({ vertical: 'study', status: 'clipped' }))).toEqual([
      'done',
      'shelve',
      'remove',
    ]);
    expect(rowActions(app({ vertical: 'career', status: 'reviewed' }))).toEqual([
      'done',
      'shelve',
      'remove',
    ]);
  });

  it('never offers Remove on an applied row', () => {
    for (const status of ['applied', 'interviewing', 'offer']) {
      expect(rowActions(app({ vertical: 'career', status }))).toEqual([]);
    }
  });

  it('offers Done and Reopen on a shelved row', () => {
    expect(rowActions(app({ vertical: 'study', status: 'shelved' }))).toEqual(['done', 'reopen']);
    expect(rowActions(app({ vertical: 'personal', status: 'shelved' }))).toEqual([
      'done',
      'reopen',
    ]);
  });

  it('keeps Done and Shelve, without Remove, on everything else live', () => {
    /* a personal quest was never clipped, so there is nothing to remove */
    expect(rowActions(app({ vertical: 'personal', status: 'found' }))).toEqual(['done', 'shelve']);
    expect(rowActions(app({ vertical: 'study', status: 'booked' }))).toEqual(['done', 'shelve']);
  });

  it('offers nothing on done rows; they live in the ledger', () => {
    expect(rowActions(app({ vertical: 'study', status: 'attended' }))).toEqual([]);
    expect(rowActions(app({ vertical: 'study', status: 'paid_out' }))).toEqual([]);
  });
});

describe('card grammar', () => {
  it('reopens a personal quest as open and a clip as clipped', () => {
    expect(reopenStatus(app({ vertical: 'personal' }))).toBe('found');
    expect(reopenStatus(app({ vertical: 'study' }))).toBe('clipped');
  });

  it('writes the follow-up line only from a real applied date', () => {
    const applied = app({
      vertical: 'career',
      status: 'applied',
      date_applied: '2026-06-30T12:00:00Z',
    });
    expect(followUpLine(applied)).toBe(
      'Applied Jun 30. A short follow-up is fair game after Jul 7. One note is plenty.',
    );
    expect(followUpLine(app({ vertical: 'career', status: 'applied' }))).toBeNull();
    expect(followUpLine(app({ vertical: 'career', status: 'clipped' }))).toBeNull();
  });
});

describe('the email row', () => {
  it('appears once the log holds a personal quest or two board rows', () => {
    const empty = splitLog([], []);
    expect(hasLogValue(empty)).toBe(false);
    const onePersonal = splitLog([app({ id: 1 })], []);
    expect(hasLogValue(onePersonal)).toBe(true);
    const oneClip = splitLog([], [app({ id: 2, vertical: 'study', status: 'clipped' })]);
    expect(hasLogValue(oneClip)).toBe(false);
    const twoClips = splitLog([], [
      app({ id: 2, vertical: 'study', status: 'clipped' }),
      app({ id: 3, vertical: 'career', status: 'applied' }),
    ]);
    expect(hasLogValue(twoClips)).toBe(true);
  });

  it('walks row, email, sent and persists in this browser', () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
    expect(readSignupState(storage)).toBe('row');
    expect(saveSignupEmail(storage, 'not an email')).toBe(false);
    expect(saveSignupEmail(storage, 'reader@example.com')).toBe(true);
    expect(readSignupState(storage)).toBe('sent');

    const store2 = new Map<string, string>();
    const storage2 = {
      getItem: (k: string) => store2.get(k) ?? null,
      setItem: (k: string, v: string) => void store2.set(k, v),
    };
    dismissSignup(storage2);
    expect(readSignupState(storage2)).toBe('dismissed');
  });

  it('checks the email shape', () => {
    expect(isPlausibleEmail('reader@example.com')).toBe(true);
    expect(isPlausibleEmail('reader@example')).toBe(false);
    expect(isPlausibleEmail('')).toBe(false);
  });
});

describe('personal quests never leak into career surfaces', () => {
  it('keeps the board vocabulary free of the personal lane', () => {
    /* the board career chip's exact query */
    expect(verticalParams('career').vertical).toBe('career');
    /* the board's All chip and every vertical chip */
    expect(ALL_VERTICALS).not.toContain('personal');
    for (const key of VERTICAL_KEYS) {
      expect(verticalParams(key).vertical).not.toContain('personal');
    }
  });

  it('only the personal log query opts into the personal lane', () => {
    expect(personalLogFilters().vertical).toBe('personal');
    expect(boardLogFilters().vertical).not.toContain('personal');
  });
});
