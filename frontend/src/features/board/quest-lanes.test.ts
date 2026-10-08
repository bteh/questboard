import { describe, expect, it } from 'vitest';
import type { KindSummary } from '@/api/board';
import { railLanes } from './quest-lanes';
import { kindParams, normalizeFacetKey, normalizeKindKey, workflowForKind } from './kind-params';

function kind(id: string, count: number, order: number, new_today = 0): KindSummary {
  return { id, label: id, sub: `${id} sub`, hue: '#000', order, count, new_today };
}

describe('the Small jobs lane', () => {
  /* Owner, Oct 2026: "acting gigs or small jobs in the meantime" were hard
     to find. Bring a skill had 1 quest, Odd jobs and Deliver & drive showed
     no tile at all. One lane gathers them. */
  it('folds odd, skill, and deliver into one tile with a summed count', () => {
    const lanes = railLanes([
      kind('think', 12, 1),
      kind('skill', 1, 5),
      kind('perform', 4, 6),
      kind('odd', 3, 9, 2),
      kind('deliver', 0, 10),
    ]);
    expect(lanes.map((l) => l.id)).toEqual(['think', 'small', 'perform']);
    const small = lanes.find((l) => l.id === 'small')!;
    expect(small).toMatchObject({ label: 'Small jobs', count: 4, new_today: 2, stamp: 'odd' });
  });

  it('stays off the rail when none of its kinds has anything live', () => {
    const lanes = railLanes([kind('think', 12, 1), kind('skill', 0, 5), kind('odd', 0, 9)]);
    expect(lanes.map((l) => l.id)).toEqual(['think']);
  });

  it('keeps career rows off the rail', () => {
    expect(railLanes([kind('work', 7, 14)])).toEqual([]);
  });

  it('queries every stored vertical of its three kinds', () => {
    const values = (kindParams('small').vertical ?? '').split(',');
    expect(values).toEqual(expect.arrayContaining(['odd', 'skill', 'lens', 'deliver']));
    expect(values).not.toContain('think');
  });

  it('is a Side Quests lane that old kind links land on', () => {
    expect(workflowForKind('small')).toBe('quests');
    expect(normalizeKindKey('deliver')).toBe('small');
    expect(normalizeKindKey('lens')).toBe('small');
    expect(normalizeKindKey('think')).toBe('think');
  });
});

describe('the Part-time lane', () => {
  /* Owner, Oct 2026: barista, boba, and restaurant shifts near Koreatown.
     It is its own tile, never folded into Small jobs. */
  it('gets its own tile with its own stamp', () => {
    const lanes = railLanes([kind('odd', 2, 9), kind('parttime', 34, 15), kind('work', 7, 16)]);
    expect(lanes.map((l) => l.id)).toEqual(['small', 'parttime']);
    expect(lanes[1]).toMatchObject({ count: 34, stamp: 'parttime' });
  });

  it('queries its own rows, rides the default board, and keeps its facets', () => {
    expect(kindParams('parttime')).toEqual({ vertical: 'parttime', upcoming_only: true });
    expect((kindParams('all').vertical ?? '').split(',')).toContain('parttime');
    expect((kindParams('small').vertical ?? '').split(',')).not.toContain('parttime');
    expect(normalizeKindKey('parttime')).toBe('parttime');
    expect(workflowForKind('parttime')).toBe('quests');
    expect(normalizeFacetKey('parttime', 'cafe')).toBe('cafe');
    expect(normalizeFacetKey('parttime', 'pets')).toBeUndefined();
  });
});
