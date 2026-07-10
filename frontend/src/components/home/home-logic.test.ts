import { describe, expect, it } from 'vitest';
import { logStripTiles, pickBounty } from './home-logic';
import type { ApplicationResponse } from '@/types/application';

function mk(id: number, extra: Partial<ApplicationResponse> = {}): ApplicationResponse {
  return { id, ...extra } as unknown as ApplicationResponse;
}

describe('pickBounty', () => {
  const study = mk(1, { salary_max: 450, date_found: '2026-07-08T10:00:00' });
  const career = mk(2, {
    salary_min: 170_000,
    salary_max: 210_000,
    date_found: '2026-07-07T10:00:00',
  });
  const noPay = mk(3, { date_found: '2026-07-08T12:00:00' });

  it('picks the highest stated pay among the recent rows', () => {
    const pick = pickBounty([study, career, noPay], []);
    expect(pick?.app.id).toBe(2);
    expect(pick?.fallback).toBe(false);
  });

  it('is deterministic regardless of input order', () => {
    const a = pickBounty([study, career, noPay], []);
    const b = pickBounty([noPay, career, study], []);
    const c = pickBounty([career, noPay, study], []);
    expect(a?.app.id).toBe(2);
    expect(b?.app.id).toBe(2);
    expect(c?.app.id).toBe(2);
  });

  it('prefers annualized pay over raw session numbers when both exist', () => {
    const hourly = mk(4, {
      salary_min: 80,
      salary_max: 95,
      salary_min_annualized: 166_400,
      salary_max_annualized: 197_600,
      date_found: '2026-07-08T09:00:00',
    });
    expect(pickBounty([study, hourly], [])?.app.id).toBe(4);
  });

  it('breaks a pay tie by the newer find, then the higher id', () => {
    const older = mk(5, { salary_min: 500, date_found: '2026-07-06T10:00:00' });
    const newer = mk(6, { salary_min: 500, date_found: '2026-07-08T10:00:00' });
    expect(pickBounty([older, newer], [])?.app.id).toBe(6);
    expect(pickBounty([newer, older], [])?.app.id).toBe(6);

    const twinA = mk(7, { salary_min: 500, date_found: '2026-07-08T10:00:00' });
    const twinB = mk(8, { salary_min: 500, date_found: '2026-07-08T10:00:00' });
    expect(pickBounty([twinB, twinA], [])?.app.id).toBe(8);
  });

  it('never invents a bounty: no recent stated pay falls back honestly', () => {
    const pick = pickBounty([noPay], [noPay, career, study]);
    expect(pick?.app.id).toBe(1);
    expect(pick?.fallback).toBe(true);
  });

  it('the fallback takes the newest stated-pay row, not the richest', () => {
    /* study (Jul 8) is newer than career (Jul 7): newest wins in fallback */
    const pick = pickBounty([], [career, study]);
    expect(pick?.app.id).toBe(1);
    expect(pick?.fallback).toBe(true);
  });

  it('returns null when nothing on the board states pay', () => {
    expect(pickBounty([noPay], [noPay])).toBeNull();
    expect(pickBounty([], [])).toBeNull();
  });
});

describe('logStripTiles', () => {
  it('builds tiles from real status counts', () => {
    expect(logStripTiles({ applied: 3, interviewing: 1, offers: 2 })).toEqual([
      { label: 'Applications out', count: 3 },
      { label: 'Interviewing', count: 1 },
      { label: 'Offers', count: 2 },
    ]);
  });

  it('hides zero tiles instead of printing empty zeros', () => {
    expect(logStripTiles({ applied: 3, interviewing: 0, offers: 0 })).toEqual([
      { label: 'Applications out', count: 3 },
    ]);
  });

  it('hides everything when the log is quiet', () => {
    expect(logStripTiles({ applied: 0, interviewing: 0, offers: 0 })).toEqual([]);
    expect(logStripTiles({})).toEqual([]);
  });

  it('treats counts that have not loaded as absent', () => {
    expect(logStripTiles({ applied: undefined, interviewing: 1 })).toEqual([
      { label: 'Interviewing', count: 1 },
    ]);
  });
});
