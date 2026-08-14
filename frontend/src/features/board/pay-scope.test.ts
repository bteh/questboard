import { describe, expect, it } from 'vitest';

import { payScopeNote } from '@/features/board/pay-scope';

describe('payScopeNote', () => {
  it('names the saved floor, which applies on every view including chips', () => {
    // Chips narrow the saved lane since 2026-08-14; the old "floor is off
    // while browsing" admission described behavior that no longer exists.
    expect(payScopeNote({ savedFloor: 190000, typedFloor: null })).toBe(
      '$190K+ base from your search',
    );
  });

  it('says nothing once you type your own minimum: the box shows it', () => {
    expect(payScopeNote({ savedFloor: 190000, typedFloor: 200000 })).toBeNull();
  });

  it('says nothing when no floor is saved', () => {
    expect(payScopeNote({ savedFloor: null, typedFloor: null })).toBeNull();
    expect(payScopeNote({ savedFloor: undefined, typedFloor: null })).toBeNull();
    expect(payScopeNote({ savedFloor: 0, typedFloor: null })).toBeNull();
  });

  it('rounds to whole thousands, matching the receipt wording', () => {
    expect(payScopeNote({ savedFloor: 175000, typedFloor: null })).toBe(
      '$175K+ base from your search',
    );
  });
});
