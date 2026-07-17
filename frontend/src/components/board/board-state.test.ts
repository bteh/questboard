import { afterEach, describe, expect, it } from 'vitest';
import {
  BOARD_NOTICE_KEY,
  BOARD_STATE_KEY,
  dismissNotice,
  hasBoardParams,
  noticeDismissed,
  presetKeysFrom,
  presetKeysTo,
  readSavedBoardState,
  saveBoardState,
  validateBoardSearch,
} from './board-state';

type MutableGlobal = Record<string, unknown>;

function stubStorage(initial: Record<string, string> = {}): Map<string, string> {
  const store = new Map(Object.entries(initial));
  (globalThis as MutableGlobal).window = {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    },
  };
  return store;
}

function stubBrokenStorage(): void {
  (globalThis as MutableGlobal).window = {
    localStorage: {
      getItem: () => {
        throw new Error('storage refused');
      },
      setItem: () => {
        throw new Error('storage refused');
      },
    },
  };
}

afterEach(() => {
  delete (globalThis as MutableGlobal).window;
});

const PRESET_ORDER = ['noexp', 'remote', 'fresh'];

describe('validateBoardSearch', () => {
  it('carries the place filter and drops an empty one', () => {
    expect(validateBoardSearch({ place: 'Los Angeles' }).place).toBe('Los Angeles');
    expect(validateBoardSearch({ place: '' }).place).toBeUndefined();
  });

  it('normalizes near me only however the router round-trips it', () => {
    // ?near=1 can come back as a string, the number 1, or a boolean
    expect(validateBoardSearch({ place: 'Chicago', near: '1' }).near).toBe('1');
    expect(validateBoardSearch({ place: 'Chicago', near: 1 }).near).toBe('1');
    expect(validateBoardSearch({ place: 'Chicago', near: true }).near).toBe('1');
    expect(validateBoardSearch({ near: 0 }).near).toBeUndefined();
    expect(validateBoardSearch({ near: '0' }).near).toBeUndefined();
    expect(validateBoardSearch({}).near).toBeUndefined();
  });

  it('keeps known verticals and drops junk', () => {
    expect(validateBoardSearch({ v: 'perform' }).v).toBe('perform');
    /* legacy vertical values from old URLs and saved state keep working */
    expect(validateBoardSearch({ v: 'camera' }).v).toBe('perform');
    expect(validateBoardSearch({ v: 'career' }).v).toBe('work');
    expect(validateBoardSearch({ v: 'lens' }).v).toBe('skill');
    expect(validateBoardSearch({ v: 'party-bus' }).v).toBeUndefined();
    expect(validateBoardSearch({ v: 42 }).v).toBeUndefined();
  });

  it('treats all as the default, not a param', () => {
    expect(validateBoardSearch({ v: 'all' }).v).toBeUndefined();
  });

  it('threads a facet only alongside the kind that carries it', () => {
    expect(validateBoardSearch({ v: 'lookafter', f: 'pets' }).f).toBe('pets');
    /* a legacy kind spelling normalizes first, then the facet check runs */
    expect(validateBoardSearch({ v: 'camera', f: 'casting' }).f).toBe('casting');
    /* another kind's facet, junk, or a facet with no kind all drop */
    expect(validateBoardSearch({ v: 'lookafter', f: 'casting' }).f).toBeUndefined();
    expect(validateBoardSearch({ v: 'lookafter', f: '' }).f).toBeUndefined();
    expect(validateBoardSearch({ f: 'pets' }).f).toBeUndefined();
  });

  it('keeps text params and drops empties', () => {
    const params = validateBoardSearch({ q: 'editor', from: '150k', to: '', p: 'remote' });
    expect(params).toEqual({ v: undefined, q: 'editor', from: '150k', to: undefined, p: 'remote' });
  });

  it('parses ?job however the router round-trips it, dropping junk', () => {
    expect(validateBoardSearch({ job: 123 }).job).toBe(123);
    expect(validateBoardSearch({ job: '123' }).job).toBe(123);
    expect(validateBoardSearch({ job: 'abc' }).job).toBeUndefined();
    expect(validateBoardSearch({ job: -4 }).job).toBeUndefined();
    expect(validateBoardSearch({}).job).toBeUndefined();
  });

  it('never persists an open detail sheet', () => {
    expect(hasBoardParams({ job: 123 })).toBe(false);
  });
});

describe('hasBoardParams', () => {
  it('is false for a bare board', () => {
    expect(hasBoardParams({})).toBe(false);
    expect(hasBoardParams(validateBoardSearch({}))).toBe(false);
  });

  it('is true for any set param', () => {
    expect(hasBoardParams({ q: 'editor' })).toBe(true);
    expect(hasBoardParams({ v: 'study' })).toBe(true);
    expect(hasBoardParams({ v: 'lookafter', f: 'pets' })).toBe(true);
    expect(hasBoardParams({ p: 'noexp' })).toBe(true);
  });
});

describe('preset keys round-trip', () => {
  it('serializes the active set in canonical order', () => {
    const keys = new Set(['remote', 'noexp']);
    expect(presetKeysTo(keys, PRESET_ORDER)).toBe('noexp,remote');
  });

  it('an empty set serializes to nothing', () => {
    expect(presetKeysTo(new Set(), PRESET_ORDER)).toBeUndefined();
  });

  it('parses back to the same set, dropping unknown keys', () => {
    const parsed = presetKeysFrom('noexp,remote,hacked', PRESET_ORDER);
    expect(parsed).toEqual(new Set(['noexp', 'remote']));
  });

  it('round-trips exactly', () => {
    const keys = new Set(['fresh', 'noexp']);
    const wire = presetKeysTo(keys, PRESET_ORDER);
    expect(presetKeysFrom(wire, PRESET_ORDER)).toEqual(keys);
  });
});

describe('board state persistence', () => {
  it('round-trips through localStorage', () => {
    stubStorage();
    saveBoardState({ v: 'perform', q: 'seat', p: 'noexp', sort: 'score' });
    expect(readSavedBoardState()).toEqual({
      v: 'perform',
      q: 'seat',
      from: undefined,
      to: undefined,
      p: 'noexp',
      sort: 'score',
    });
  });

  it('drops empty fields on write', () => {
    const store = stubStorage();
    saveBoardState({ q: 'editor' });
    expect(JSON.parse(store.get(BOARD_STATE_KEY)!)).toEqual({ q: 'editor' });
  });

  it('persists a facet with its kind and validates it on read', () => {
    stubStorage();
    saveBoardState({ v: 'lookafter', f: 'pets' });
    expect(readSavedBoardState()?.f).toBe('pets');
    /* a saved facet from a kind that no longer carries it drops on read */
    stubStorage({ [BOARD_STATE_KEY]: JSON.stringify({ v: 'think', f: 'pets' }) });
    expect(readSavedBoardState()?.f).toBeUndefined();
  });

  it('reads null when nothing is saved', () => {
    stubStorage();
    expect(readSavedBoardState()).toBeNull();
  });

  it('reads null on corrupted storage', () => {
    stubStorage({ [BOARD_STATE_KEY]: 'not json' });
    expect(readSavedBoardState()).toBeNull();
  });

  it('validates saved values the same as URL params', () => {
    stubStorage({ [BOARD_STATE_KEY]: JSON.stringify({ v: 'bogus', q: 'ok', sort: 'sideways' }) });
    expect(readSavedBoardState()).toEqual({
      v: undefined,
      q: 'ok',
      from: undefined,
      to: undefined,
      p: undefined,
    });
  });

  it('survives a browser that refuses storage', () => {
    stubBrokenStorage();
    expect(() => saveBoardState({ q: 'editor' })).not.toThrow();
    expect(readSavedBoardState()).toBeNull();
  });
});

describe('the first-run notice', () => {
  it('shows until dismissed', () => {
    stubStorage();
    expect(noticeDismissed()).toBe(false);
    dismissNotice();
    expect(noticeDismissed()).toBe(true);
  });

  it('persists the dismissal', () => {
    const store = stubStorage();
    dismissNotice();
    expect(store.get(BOARD_NOTICE_KEY)).toBe('1');
  });

  it('survives a browser that refuses storage', () => {
    stubBrokenStorage();
    expect(noticeDismissed()).toBe(false);
    expect(() => dismissNotice()).not.toThrow();
  });
});
