import { describe, expect, it } from 'vitest';

import { assistantNote, installUrlFor } from './assistant-links';

describe('assistant links', () => {
  it('sends the desktop-app user to the app download, not to a terminal tool', () => {
    expect(installUrlFor('claude_desktop')).toBe('https://claude.ai/download');
    expect(installUrlFor('claude')).toBe('https://claude.ai/code');
  });

  it('says plainly that the desktop app works on a free account', () => {
    expect(assistantNote('claude_desktop')).toMatch(/free/i);
    expect(assistantNote('claude')).toMatch(/Pro or Max/);
  });
});
