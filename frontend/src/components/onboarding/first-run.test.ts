// @vitest-environment jsdom
/* The first-run hand-off is a two-party agreement: the onboarding wizard
   marks the flag, the restock page consumes it once and opens the results.
   This pins both sides to the same key, so the moment can actually fire. */

import { beforeEach, describe, expect, it } from 'vitest';
import { consumeFirstRunPending, markFirstRunPending } from './first-run';

describe('the first-run hand-off flag', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('fires once after the wizard marks it, then stays quiet', () => {
    markFirstRunPending();
    expect(consumeFirstRunPending()).toBe(true);
    expect(consumeFirstRunPending()).toBe(false);
  });

  it('stays quiet when nothing was marked', () => {
    expect(consumeFirstRunPending()).toBe(false);
  });

  it('writes the key the restock page actually reads', () => {
    markFirstRunPending();
    expect(window.localStorage.getItem('questboard:first-run-pending')).toBe('1');
  });

  it('clears the orphaned onboarding-complete key nothing ever read', () => {
    window.localStorage.setItem('questboard:onboarding-complete', '1');
    markFirstRunPending();
    expect(window.localStorage.getItem('questboard:onboarding-complete')).toBeNull();
  });
});
