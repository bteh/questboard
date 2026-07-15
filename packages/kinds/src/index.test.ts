import { describe, expect, it } from 'vitest';
import raw from '../kinds.json';
import { KINDS, KIND_IDS, facetsFor, kindById, kindForVertical, verticalValuesFor } from './index';

describe('the kinds registry', () => {
  it('exposes every kind from kinds.json, sorted by order', () => {
    expect(KINDS.length).toBe(raw.kinds.length);
    expect(KINDS.map((k) => k.order)).toEqual([...KINDS.map((k) => k.order)].sort((a, b) => a - b));
  });

  it('has unique ids, unique orders, and no blank labels or subs', () => {
    expect(new Set(KIND_IDS).size).toBe(KINDS.length);
    expect(new Set(KINDS.map((k) => k.order)).size).toBe(KINDS.length);
    for (const kind of KINDS) {
      expect(kind.label.trim()).not.toBe('');
      expect(kind.sub.trim()).not.toBe('');
      expect(kind.hue).toMatch(/^#[0-9A-F]{6}$/i);
    }
  });

  it('maps every legacy vertical to exactly one kind', () => {
    const seen = new Map<string, string>();
    for (const kind of KINDS) {
      for (const legacy of kind.legacy_verticals) {
        expect(seen.has(legacy), `legacy vertical "${legacy}" claimed twice`).toBe(false);
        seen.set(legacy, kind.id);
      }
    }
    // career now lives in its own `work` lane, split out of skill so the
    // default quest board never shows job postings; lens (freelance/gigs)
    // stays a real side-quest under skill
    expect(kindForVertical('career')?.id).toBe('work');
    expect(kindForVertical('lens')?.id).toBe('skill');
    expect(kindForVertical('study')?.id).toBe('think');
    expect(kindForVertical('camera')?.id).toBe('perform');
    expect(kindForVertical('party')?.id).toBe('party');
  });

  it('treats kind ids as identity so new sources can write them directly', () => {
    for (const kind of KINDS) {
      expect(kindForVertical(kind.id)?.id).toBe(kind.id);
    }
  });

  it('answers the stored-value expansion the API needs', () => {
    expect(verticalValuesFor('skill').sort()).toEqual(['lens', 'skill']);
    expect(verticalValuesFor('work').sort()).toEqual(['career', 'work']);
    expect(verticalValuesFor('nope')).toEqual([]);
    expect(kindById('body')?.label).toBe('Join a study');
  });

  it('keeps audience as its own kind, right after perform', () => {
    // audience seats are loved but they are a different quest from casting
    const ids = KINDS.map((k) => k.id);
    expect(ids.indexOf('audience')).toBe(ids.indexOf('perform') + 1);
    expect(kindById('audience')?.hue).not.toBe(kindById('perform')?.hue);
    expect(kindById('audience')?.legacy_verticals).toEqual([]);
    // camera stays perform's legacy value so old rows keep resolving there
    expect(kindForVertical('camera')?.id).toBe('perform');
  });

  it('exposes facets with terms, and [] for kinds without any', () => {
    expect(facetsFor('lookafter').map((f) => f.id)).toEqual(['pets', 'kids', 'houses']);
    for (const kind of KINDS) {
      for (const facet of kind.facets) {
        expect(facet.label.trim()).not.toBe('');
        expect(facet.terms.length).toBeGreaterThan(0);
      }
    }
    expect(facetsFor('odd')).toEqual([]);
    expect(facetsFor('nope')).toEqual([]);
    // legacy spellings resolve to their kind's facets
    expect(facetsFor('camera').map((f) => f.id)).toEqual(['casting', 'voice', 'music']);
  });
});
