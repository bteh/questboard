/** The copyable prompt is the manual path: it runs in the user's own
 * unrestricted client where no tool allow or deny list applies. When the
 * headless run went proposal-based, this prompt still said "save them", which
 * kept the exact silent-rewrite behavior alive for anyone who pastes it.
 * The saved search is user-owned on every path, not just the automatic one. */
import { describe, expect, it } from 'vitest';

import { SETUP_PROMPT } from '@/components/settings/AssistantTab';

describe('the copyable assistant prompt', () => {
  it('never instructs saving my preferences', () => {
    const lower = SETUP_PROMPT.toLowerCase();
    // Every mention of saving must be a negation; a bare "save them" is the
    // old instruction that silently rewrote the saved search.
    const saves = lower.split('save them').length - 1;
    const negated = lower.split('not save them').length - 1;
    expect(saves).toBe(negated);
    expect(negated).toBeGreaterThan(0);
    expect(SETUP_PROMPT).not.toContain('set_career_preferences');
  });

  it('asks for a proposal instead', () => {
    expect(SETUP_PROMPT).toContain('propose');
  });

  it('still runs the search with the sharpened roles for this run', () => {
    expect(SETUP_PROMPT.toLowerCase()).toContain('refresh work with those roles');
  });
});
