// @vitest-environment jsdom
/* The first-run hand-off is a two-party agreement: the onboarding wizard
   marks the flag, the board's Find work lane consumes it once and pulls the
   first jobs. This pins both sides to the same key, so the moment can fire. */

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

  it('writes the key the board work lane actually reads', () => {
    markFirstRunPending();
    expect(window.localStorage.getItem('questboard:first-run-pending')).toBe('1');
  });

  it('clears the orphaned onboarding-complete key nothing ever read', () => {
    window.localStorage.setItem('questboard:onboarding-complete', '1');
    markFirstRunPending();
    expect(window.localStorage.getItem('questboard:onboarding-complete')).toBeNull();
  });
});
