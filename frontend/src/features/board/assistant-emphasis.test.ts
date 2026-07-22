/* One primary action on the work lane: "Get new jobs" stays the only filled
   button. The assistant run door is quiet at zero rows, elevated only when
   rows exist and no verdicts are stored yet, and quiet again once ranked. */

import { describe, expect, it } from 'vitest';
import { assistantRunEmphasis } from './assistant-run-button';

describe('the assistant run button emphasis', () => {
  it('stays quiet when the lane has zero rows', () => {
    expect(assistantRunEmphasis(0, false)).toBe('quiet');
    expect(assistantRunEmphasis(0, true)).toBe('quiet');
  });

  it('elevates when rows exist and nothing is ranked yet', () => {
    expect(assistantRunEmphasis(1, false)).toBe('elevated');
    expect(assistantRunEmphasis(24, false)).toBe('elevated');
  });

  it('goes quiet again once verdicts are stored', () => {
    expect(assistantRunEmphasis(24, true)).toBe('quiet');
  });
});
