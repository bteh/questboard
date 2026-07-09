/* The poster model's honesty rules: kinds resolve from stored verticals,
   the scannable line is the posting's own text or nothing, requirements
   never cross-contaminate kinds, and the beginner treatment only appears
   when the source stated it. */

import { describe, expect, it } from 'vitest';
import { rotationFor, scannableDesc, toPoster } from './poster-model';
import { kindParams, normalizeKindKey } from './kind-params';
import type { ApplicationResponse } from '@/types/application';

function app(overrides: Partial<ApplicationResponse>): ApplicationResponse {
  return {
    id: 7,
    job_title: 'Snack focus group',
    company: 'Fieldwork',
    location: 'Chicago',
    job_url: 'https://example.com/q',
    source: 'focusgroups_org',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
    salary_currency: '',
    salary_period: '',
    overall_score: null,
    recommendation: '',
    status: 'found',
    vertical: 'study',
    first_quest_ok: false,
    ...overrides,
  } as ApplicationResponse;
}

describe('the poster model', () => {
  it('maps stored verticals onto kinds', () => {
    expect(toPoster(app({ vertical: 'study' }), 'Fieldwork').kind).toBe('think');
    expect(toPoster(app({ vertical: 'camera' }), 'x').kind).toBe('perform');
    expect(toPoster(app({ vertical: 'career' }), 'x').kind).toBe('skill');
    expect(toPoster(app({ vertical: 'lens' }), 'x').kind).toBe('skill');
  });

  it('never asks a focus group for a resume', () => {
    const poster = toPoster(app({ vertical: 'study' }), 'Fieldwork');
    expect(poster.copy.bring).toContain('no resume');
    expect(poster.hasFit).toBe(false);
  });

  it('gives the beginner treatment only on the stated signal', () => {
    const plain = toPoster(app({ vertical: 'camera' }), 'x');
    expect(plain.copy.bringFree).toBeUndefined();
    const stated = toPoster(app({ vertical: 'camera', first_quest_ok: true }), 'x');
    expect(stated.copy.bringFree).toBe(true);
    expect(stated.copy.bring).toContain('nothing');
  });

  it('cuts the scannable line from real text or renders nothing', () => {
    expect(scannableDesc('')).toBeUndefined();
    expect(scannableDesc('   ')).toBeUndefined();
    expect(scannableDesc('React to a new snack. Then more detail here.')).toBe(
      'React to a new snack.',
    );
    const long = 'a'.repeat(200);
    expect(scannableDesc(long)!.length).toBeLessThanOrEqual(140);
  });

  it('tilts each poster deterministically within the tack-up range', () => {
    for (const id of [1, 2, 3, 99, 1234]) {
      const deg = rotationFor(id);
      expect(deg).toBe(rotationFor(id));
      expect(Math.abs(deg)).toBeLessThanOrEqual(1.5);
    }
  });
});

describe('kind params', () => {
  it('expands a kind to every stored value it answers to', () => {
    expect(kindParams('skill').vertical!.split(',').sort()).toEqual(['career', 'lens', 'skill']);
    expect(kindParams('think').vertical).toContain('study');
  });

  it('normalizes legacy vertical values from old URLs', () => {
    expect(normalizeKindKey('camera')).toBe('perform');
    expect(normalizeKindKey('perform')).toBe('perform');
    expect(normalizeKindKey('all')).toBeUndefined();
    expect(normalizeKindKey('bogus')).toBeUndefined();
  });
});
