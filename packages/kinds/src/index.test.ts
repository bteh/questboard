import { describe, expect, it } from 'vitest';
import raw from '../kinds.json';
import { KINDS, KIND_IDS, kindById, kindForVertical, verticalValuesFor } from './index';

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
});
