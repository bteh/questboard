import { describe, expect, it } from 'vitest';
import { isCareerKind, kindParams, normalizeFacetKey, questTotal } from './kind-params';

describe('the board kind params', () => {
  it('keeps career out of the default "all quests" board', () => {
    const values = (kindParams('all').vertical ?? '').split(',');
    // real side-quest verticals are in
    expect(values).toContain('study');
    expect(values).toContain('lens');
    expect(values).toContain('skill');
    // career job postings are not: the default board is quests only
    expect(values).not.toContain('career');
    expect(values).not.toContain('work');
  });

  it('routes the Jobs lane to career rows (old and new vertical values)', () => {
    const values = (kindParams('work').vertical ?? '').split(',');
    expect(values).toContain('career');
    expect(values).toContain('work');
  });

  it('names career kinds and nothing else', () => {
    expect(isCareerKind('work')).toBe(true);
    expect(isCareerKind('skill')).toBe(false);
    expect(isCareerKind('all')).toBe(false);
    expect(isCareerKind(undefined)).toBe(false);
  });

  it('counts "all quests" as side-quests only, never the Jobs lane', () => {
    const kinds = [
      { id: 'think', count: 40 },
      { id: 'skill', count: 12 },
      { id: 'work', count: 999 },
    ];
    expect(questTotal(kinds)).toBe(52);
  });

  it('keeps upcoming_only on so stale tapings never show', () => {
    expect(kindParams('all').upcoming_only).toBe(true);
    expect(kindParams('work').upcoming_only).toBe(true);
  });

  it('keeps a facet only when the kind carries it', () => {
    expect(normalizeFacetKey('lookafter', 'pets')).toBe('pets');
    // another kind's facet, junk, and facets without a kind all drop
    expect(normalizeFacetKey('lookafter', 'casting')).toBeUndefined();
    expect(normalizeFacetKey('lookafter', 'party-bus')).toBeUndefined();
    expect(normalizeFacetKey('all', 'pets')).toBeUndefined();
    expect(normalizeFacetKey(undefined, 'pets')).toBeUndefined();
    expect(normalizeFacetKey('perform', 'casting')).toBe('casting');
  });
});
