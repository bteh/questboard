/* After a run, the panel must say what happened. A run that ends with no
   pending proposal shows the assistant's own one-line answer, trimmed. */
import { describe, expect, it } from 'vitest';

import { PROPOSE_ROLES_PROMPT, runOutcomeNote } from './suggest-roles-logic';

const ok = (result: string) => ({ ok: true, result, error: '', cost_usd: null, num_turns: 2 });

describe('runOutcomeNote', () => {
  it('returns the answer when nothing is pending', () => {
    expect(runOutcomeNote(ok('Your roles already fit; nothing new.'), 0)).toBe('Your roles already fit; nothing new.');
  });

  it('stays quiet when a proposal is there to act on', () => {
    expect(runOutcomeNote(ok('Proposed four roles.'), 1)).toBeNull();
  });

  it('stays quiet on failure, which the toast reports', () => {
    expect(runOutcomeNote({ ok: false, result: '', error: 'not signed in', cost_usd: null, num_turns: null }, 0)).toBeNull();
  });

  it('trims a long answer to a readable line', () => {
    const note = runOutcomeNote(ok('word '.repeat(120)), 0);
    expect(note).not.toBeNull();
    expect((note as string).length).toBeLessThanOrEqual(281);
    expect(note as string).toMatch(/…$/);
  });

  it('falls back to a plain sentence when the answer is empty', () => {
    expect(runOutcomeNote(ok('   '), 0)).toBe('Finished, but nothing new to suggest.');
  });
});

describe('PROPOSE_ROLES_PROMPT', () => {
  it('asks for keywords as well as roles', () => {
    expect(PROPOSE_ROLES_PROMPT.toLowerCase()).toContain('keywords');
  });
});
