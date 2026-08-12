/* The poster model's honesty rules: kinds resolve from stored verticals,
   the scannable line is the posting's own text or nothing, requirements
   never cross-contaminate kinds, and the beginner treatment only appears
   when the source stated it. */

import { describe, expect, it } from 'vitest';
import {
  fitDigest,
  fitGroups,
  newestFirst,
  rotationFor,
  scannableDesc,
  toPoster,
} from './poster-model';
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

  it('adds honest effort and criteria to Side Quests, never career jobs', () => {
    const quest = toPoster(app({ vertical: 'scholarship' }), 'Scholarship America');
    expect(quest.requirements?.effort).toMatchObject({
      level: 'involved',
      basis: 'typical',
    });
    expect(quest.requirements?.criteria.items[0]).toContain('eligibility proof');
    expect(toPoster(app({ vertical: 'career' }), 'BuiltIn').requirements).toBeUndefined();
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

  it('strips stored markup junk before cutting the scannable line', () => {
    const dirty =
      '**Own** the pipeline.\n\n### Requirements\n<div class="content-intro">5 years with Python.</div>';
    const out = scannableDesc(dirty)!;
    expect(out).toBe('Own the pipeline. Requirements 5 years with Python.');
    expect(out).not.toMatch(/\*\*|###|<|content-intro/);
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

/* fitGroups and newestFirst are structural: light rows are enough */
function fit(id: number, verdict: 'strong' | 'good' | 'reach' | 'skip', rank: number | null = null) {
  return { id, agent_fit: { rank, verdict, why: '', caveat: '' } };
}
function bare(id: number) {
  return { id, agent_fit: null };
}

describe('fitGroups', () => {
  it('orders verdict groups, rank asc inside, unranked rows after, skips last', () => {
    const rows = [
      fit(1, 'reach', 5),
      fit(2, 'strong', 3),
      fit(3, 'skip'),
      bare(4),
      fit(5, 'good'),
      fit(6, 'strong', 1),
      fit(7, 'good', 2),
      fit(8, 'skip', 9),
    ];
    const wall = fitGroups(rows);
    expect(wall.groups.map((g) => g.verdict)).toEqual(['strong', 'good', 'reach']);
    expect(wall.groups.map((g) => g.label)).toEqual(['Strong fit', 'Good fit', 'Worth a reach']);
    /* rank asc within a group */
    expect(wall.groups[0].items.map((r) => r.id)).toEqual([6, 2]);
    /* a ranked row beats an unranked one of the same verdict */
    expect(wall.groups[1].items.map((r) => r.id)).toEqual([7, 5]);
    expect(wall.groups[2].items.map((r) => r.id)).toEqual([1]);
    /* rows the assistant never judged sit after the groups */
    expect(wall.unranked.map((r) => r.id)).toEqual([4]);
    /* skips last; a ranked skip still sorts before an unranked one */
    expect(wall.skips.map((r) => r.id)).toEqual([8, 3]);
  });

  it('omits empty groups and keeps sibling order stable', () => {
    const wall = fitGroups([fit(1, 'strong'), fit(2, 'skip'), fit(3, 'strong')]);
    expect(wall.groups.map((g) => g.verdict)).toEqual(['strong']);
    /* both unranked: original order holds */
    expect(wall.groups[0].items.map((r) => r.id)).toEqual([1, 3]);
    expect(wall.skips.map((r) => r.id)).toEqual([2]);
    expect(wall.unranked).toEqual([]);
  });

  it('leaves a wall with no verdicts alone: no groups, no skips, order kept', () => {
    const rows = [bare(3), bare(1), bare(2)];
    const wall = fitGroups(rows);
    expect(wall.groups).toEqual([]);
    expect(wall.skips).toEqual([]);
    expect(wall.unranked.map((r) => r.id)).toEqual([3, 1, 2]);
  });
});

describe('fitDigest', () => {
  it('counts the loaded verdicts and drops zero groups', () => {
    const wall = fitGroups([fit(1, 'strong', 1), fit(2, 'strong', 2), fit(3, 'reach', 3), fit(4, 'skip')]);
    expect(fitDigest(wall)).toBe('Your assistant ranked 3 jobs: 2 strong, 1 reach.');
  });

  it('speaks singular for one job', () => {
    expect(fitDigest(fitGroups([fit(1, 'good', 1)]))).toBe('Your assistant ranked 1 job: 1 good.');
  });

  it('says nothing when only skips or no verdicts exist', () => {
    expect(fitDigest(fitGroups([fit(1, 'skip')]))).toBeNull();
    expect(fitDigest(fitGroups([bare(1)]))).toBeNull();
  });
});

describe('newestFirst', () => {
  it('orders loaded rows newest first, unknown dates last, ties stable', () => {
    const rows = [
      { id: 1, date_found: '2026-07-06 10:00:00' },
      { id: 2, date_found: null },
      { id: 3, date_found: '2026-07-07T09:00:00' },
      { id: 4, date_found: '2026-07-06 10:00:00' },
    ];
    expect(newestFirst(rows).map((r) => r.id)).toEqual([3, 1, 4, 2]);
    /* pure: the input array never mutates */
    expect(rows.map((r) => r.id)).toEqual([1, 2, 3, 4]);
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
