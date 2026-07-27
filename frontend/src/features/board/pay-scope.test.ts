import { describe, expect, it } from 'vitest';

import { payScopeNote } from '@/features/board/pay-scope';

describe('payScopeNote', () => {
  it('names the saved floor on the roles view, where it really applies', () => {
    expect(payScopeNote({ browsingCategory: false, savedFloor: 190000, typedFloor: null })).toBe(
      '$190K+ base from your search',
    );
  });

  it('admits the floor is off while browsing a source chip', () => {
    // Measured 2026-07-27: the Remote chip showed 632 rows, 101 of which state
    // pay under the saved $190K floor, while the receipt still said $190K+.
    expect(payScopeNote({ browsingCategory: true, savedFloor: 190000, typedFloor: null })).toBe(
      'your $190K floor is off while browsing',
    );
  });

  it('says nothing once you type your own minimum: the box shows it', () => {
    expect(payScopeNote({ browsingCategory: false, savedFloor: 190000, typedFloor: 200000 })).toBeNull();
    expect(payScopeNote({ browsingCategory: true, savedFloor: 190000, typedFloor: 200000 })).toBeNull();
  });

  it('says nothing when no floor is saved', () => {
    expect(payScopeNote({ browsingCategory: false, savedFloor: null, typedFloor: null })).toBeNull();
    expect(payScopeNote({ browsingCategory: true, savedFloor: undefined, typedFloor: null })).toBeNull();
    expect(payScopeNote({ browsingCategory: false, savedFloor: 0, typedFloor: null })).toBeNull();
  });

  it('rounds to whole thousands, matching the receipt wording', () => {
    expect(payScopeNote({ browsingCategory: false, savedFloor: 175000, typedFloor: null })).toBe(
      '$175K+ base from your search',
    );
  });
});
