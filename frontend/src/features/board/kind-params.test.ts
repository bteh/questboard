import { describe, expect, it } from 'vitest';
import {
  isCareerKind,
  kindParams,
  normalizeFacetKey,
  normalizeKindKey,
  questRefreshVerticals,
  questTotal,
  workflowForKind,
} from './kind-params';

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

  it('assigns each ?v value to its workflow tab', () => {
    // the career lane lands on the Find work tab
    expect(workflowForKind('work')).toBe('work');
    // everything else, including no kind at all, is the Side quests tab
    expect(workflowForKind('all')).toBe('quests');
    expect(workflowForKind('skill')).toBe('quests');
    expect(workflowForKind(undefined)).toBe('quests');
    // a legacy ?v=career deep link normalizes first, then lands on Find work
    expect(workflowForKind(normalizeKindKey('career'))).toBe('work');
  });

  it('refreshes quest verticals only, never the career pipeline', () => {
    const verticals = questRefreshVerticals();
    expect(verticals).toContain('think');
    expect(verticals).toContain('skill');
    // legacy stored values ride along so old-vocabulary scrapers still run
    expect(verticals).toContain('study');
    expect(verticals).not.toContain('career');
    expect(verticals).not.toContain('work');
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
