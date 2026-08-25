import { describe, expect, it } from 'vitest';
import { plainWords } from './landing-logic';
import type { ApplicationResponse } from '@/types/application';

function mk(
  id: number,
  vertical?: string,
  extra: Partial<ApplicationResponse> = { salary_min: 100 },
): ApplicationResponse {
  return { id, vertical, ...extra } as unknown as ApplicationResponse;
}

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
