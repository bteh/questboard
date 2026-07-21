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
    // career is its own Jobs lane now; lens (freelance/gigs) stays skill
    expect(toPoster(app({ vertical: 'career' }), 'x').kind).toBe('work');
    expect(toPoster(app({ vertical: 'lens' }), 'x').kind).toBe('skill');
  });

  it('career rows carry no flavor tags, and remote never doubles', () => {
    // remote/location reads on the meta line; it must not also be a tag
    expect(toPoster(app({ vertical: 'career', is_remote: true, work_type: 'remote' }), 'BuiltIn').tags)
      .toEqual([]);
  });

  it('labels only the widened role bucket as adjacent', () => {
    expect(toPoster(app({ vertical: 'career', match_bucket: 'primary' }), 'BuiltIn').tags).toEqual([]);
    expect(toPoster(app({ vertical: 'career', match_bucket: 'adjacent' }), 'BuiltIn').tags)
      .toEqual(['adjacent match']);
  });

  it('a quest keeps a work type only when it adds something the meta lacks', () => {
    expect(toPoster(app({ vertical: 'camera', is_remote: true, work_type: 'remote' }), 'x').tags).toEqual([]);
    expect(toPoster(app({ vertical: 'lens', work_type: 'hybrid' }), 'x').tags).toEqual(['hybrid']);
  });

  it('never asks a focus group for a resume', () => {
    const poster = toPoster(app({ vertical: 'study' }), 'Fieldwork');
    expect(poster.copy.bring).toContain('no resume');
    expect(poster.hasFit).toBe(false);
  });

  it("a row's stated bring and catch beat the kind template", () => {
    const stated = toPoster(
      app({
        vertical: 'flip',
        first_quest_ok: true,
        quest: { bring: 'photos of your clothes', catch: 'Poshmark takes 20% at $15 or more' },
      }),
      'Questboard',
    );
    expect(stated.copy.bring).toBe('photos of your clothes');
    expect(stated.copy.catchLine).toBe('Poshmark takes 20% at $15 or more');
    // the beginner treatment survives alongside the stated copy
    expect(stated.copy.bringFree).toBe(true);
  });

  it('gives the beginner treatment only on the stated signal', () => {
    const plain = toPoster(app({ vertical: 'camera' }), 'x');
    expect(plain.copy.bringFree).toBeUndefined();
    const stated = toPoster(app({ vertical: 'camera', first_quest_ok: true }), 'x');
    expect(stated.copy.bringFree).toBe(true);
    expect(stated.copy.bring).toContain('nothing');
  });

  it('returns a clean word-boundary lead, letting the card CSS clamp the rest', () => {
    expect(scannableDesc('')).toBeUndefined();
    expect(scannableDesc('   ')).toBeUndefined();
    // Short text is returned whole; the poster's 2-line CSS clamp does the
    // visual cut, so no mid-sentence JS truncation here.
    expect(scannableDesc('React to a new snack. Then more detail here.')).toBe(
      'React to a new snack. Then more detail here.',
    );
    // Long text: word-boundary truncation, no mid-word fragment, <= 200 chars.
    const long = 'word '.repeat(60).trim();
    const out = scannableDesc(long)!;
    expect(out.length).toBeLessThanOrEqual(200);
    expect(out.endsWith(' ')).toBe(false);
    expect(out.endsWith('word')).toBe(true);
  });

  it('gives career posters the logo well, quests the small giver logo', () => {
    const career = toPoster(app({ vertical: 'career', company: 'Stripe' }), 'BuiltIn');
    expect(career.logoWell).toBeDefined();
    expect(career.logoWell!.initial).toBe('S');
    expect(career.logoWell!.color).toMatch(/^#/);
    expect(career.logoUrl).toBeUndefined();

    const quest = toPoster(app({ vertical: 'study' }), 'Fieldwork');
    expect(quest.logoWell).toBeUndefined();

    /* placeholder company tokens never earn a monogram */
    const blank = toPoster(app({ vertical: 'career', company: 'null' }), 'BuiltIn');
    expect(blank.logoWell).toBeUndefined();
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
    expect(kindParams('skill').vertical!.split(',').sort()).toEqual(['lens', 'skill']);
    expect(kindParams('work').vertical!.split(',').sort()).toEqual(['career', 'work']);
    expect(kindParams('think').vertical).toContain('study');
  });

  it('normalizes legacy vertical values from old URLs', () => {
    expect(normalizeKindKey('camera')).toBe('perform');
    expect(normalizeKindKey('perform')).toBe('perform');
    expect(normalizeKindKey('all')).toBeUndefined();
    expect(normalizeKindKey('bogus')).toBeUndefined();
  });
});
