import { afterEach, describe, expect, it, vi } from 'vitest';
import { handleEnter, pickLandingCards, pickTrustCard, plainWords } from './landing-logic';
import { ENTERED_KEY } from '@/lib/entry';
import type { ApplicationResponse } from '@/types/application';

type MutableGlobal = Record<string, unknown>;

afterEach(() => {
  delete (globalThis as MutableGlobal).window;
});

function mk(
  id: number,
  vertical?: string,
  extra: Partial<ApplicationResponse> = { salary_min: 100 },
): ApplicationResponse {
  return { id, vertical, ...extra } as unknown as ApplicationResponse;
}

describe('handleEnter', () => {
  it('sets the entered flag and lands on the board', () => {
    const store = new Map<string, string>();
    (globalThis as MutableGlobal).window = {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
      },
    };
    const navigate = vi.fn();
    handleEnter(navigate);
    expect(store.get(ENTERED_KEY)).toBe('1');
    expect(navigate).toHaveBeenCalledWith({ to: '/board' });
  });
});

describe('plainWords', () => {
  it('builds the explain text only from the row, never inventing pay', () => {
    const noPay = mk(1, 'career', { salary_min: null, salary_max: null } as never);
    const out = plainWords(noPay, 'Greenhouse');
    expect(out.text).not.toMatch(/\$/); /* no pay stated, so no pay shown */
    expect(out.kicker).toContain('job posting');
  });

  it('restates the stated pay when the row has it', () => {
    const paid = mk(2, 'study', { salary_min: 65, salary_period: 'session' } as never);
    const out = plainWords(paid, 'FocusGroups');
    expect(out.text).toContain('$');
    expect(out.kicker).toContain('study listing');
  });
});

describe('pickLandingCards', () => {
  it('mixes verticals, newest first', () => {
    const items = [
      mk(1, 'career'),
      mk(2, 'career'),
      mk(3, 'camera'),
      mk(4, 'study'),
      mk(5, 'lens'),
    ];
    expect(pickLandingCards(items).map((a) => a.id)).toEqual([1, 3, 4]);
  });

  it('prefers stated pay over a newer card that states none', () => {
    const items = [
      mk(1, 'camera', {}) /* no pay stated */,
      mk(2, 'career'),
      mk(3, 'study'),
      mk(4, 'camera'),
    ];
    expect(pickLandingCards(items).map((a) => a.id)).toEqual([2, 3, 4]);
  });

  it('folds two rows of one kind into a single pick so another kind gets the slot', () => {
    const items = [
      mk(1, 'lens') /* skill kind */,
      mk(2, 'lens') /* also the skill kind */,
      mk(3, 'camera'),
      mk(4, 'study'),
    ];
    expect(pickLandingCards(items).map((a) => a.id)).toEqual([1, 3, 4]);
  });

  it('falls back to newest leftovers when the board is one vertical', () => {
    const items = [mk(1, 'career'), mk(2, 'career'), mk(3, 'career'), mk(4, 'career')];
    expect(pickLandingCards(items).map((a) => a.id)).toEqual([1, 2, 3]);
  });

  it('returns what exists when the board is nearly empty', () => {
    expect(pickLandingCards([mk(1, 'camera')]).map((a) => a.id)).toEqual([1]);
    expect(pickLandingCards([])).toEqual([]);
  });
});

describe('pickTrustCard', () => {
  const posted: Partial<ApplicationResponse> = {
    salary_min: 100,
    date_posted: '2026-07-01',
    date_confidence: 'exact',
  };

  it('prefers a spare row that can say its true post date', () => {
    const items = [
      mk(1, 'career', posted),
      mk(2, 'camera', posted),
      mk(3, 'study', posted),
      mk(4, 'career') /* no post date */,
      mk(5, 'lens', posted),
    ];
    const pinned = pickLandingCards(items); /* 1, 2, 3 */
    expect(pickTrustCard(items, pinned)?.id).toBe(5);
  });

  it('prefers the study shape when dates tie', () => {
    const items = [
      mk(1, 'career', posted),
      mk(2, 'camera', posted),
      mk(3, 'study', posted),
      mk(4, 'lens', posted),
      mk(5, 'study', posted),
    ];
    const pinned = pickLandingCards(items); /* 1, 2, 3: skill, perform, think */
    expect(pickTrustCard(items, pinned)?.id).toBe(5);
  });

  it('takes the newest spare row otherwise', () => {
    const items = [
      mk(1, 'career'),
      mk(2, 'camera'),
      mk(3, 'lens'),
      mk(4, 'career'),
      mk(5, 'career'),
    ];
    const pinned = pickLandingCards(items); /* 1, 2, 3 */
    expect(pickTrustCard(items, pinned)?.id).toBe(4);
  });

  it('returns null when every row is pinned', () => {
    const items = [mk(1, 'career'), mk(2, 'camera')];
    expect(pickTrustCard(items, pickLandingCards(items))).toBeNull();
  });
});
