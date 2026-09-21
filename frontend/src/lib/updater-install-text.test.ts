/* The words for the states the restart flow has: installing, an install
   that failed while the app kept working, and (Sep 21 2026 review) an
   install that landed but whose relaunch did not. */
import { describe, expect, it } from 'vitest';

import { checkStatusText, updateActionText, updateBannerText } from './updater-logic';

describe('install states in the topbar pill', () => {
  it('says it is installing, with no action to click', () => {
    expect(updateBannerText({ kind: 'installing', version: '0.2.6' })).toBe('Installing 0.2.6…');
    expect(updateActionText({ kind: 'installing', version: '0.2.6' })).toBeNull();
  });

  it('says a failed install left the app working, and offers a retry', () => {
    expect(updateBannerText({ kind: 'install_failed', version: '0.2.6' })).toBe(
      "Couldn't install 0.2.6. The app still works.",
    );
    expect(updateActionText({ kind: 'install_failed', version: '0.2.6' })).toBe('Try again');
  });

  it('keeps Restart as the action once an update is ready', () => {
    expect(updateActionText({ kind: 'ready', version: '0.2.6' })).toBe('Restart');
    expect(updateActionText({ kind: 'idle' })).toBeNull();
    expect(updateActionText({ kind: 'downloading', percent: 40 })).toBeNull();
  });
});

describe('install states in the Settings row', () => {
  it('names the version that failed and points at the website', () => {
    const text = checkStatusText({ kind: 'install_failed', version: '0.2.6' }, '0.2.5');
    expect(text).toContain("Couldn't install 0.2.6");
    expect(text.toLowerCase()).toContain('website');
  });

  it('reports installing', () => {
    expect(checkStatusText({ kind: 'installing', version: '0.2.6' }, '0.2.5')).toBe('Installing 0.2.6…');
  });
});

describe('an install that landed without a relaunch', () => {
  const installed = { kind: 'installed', version: '0.2.6' } as const;
  const words = 'Installed 0.2.6. Quit and reopen Questboard to finish.';

  it('tells the person to quit and reopen, with nothing to click', () => {
    expect(updateBannerText(installed)).toBe(words);
    expect(updateActionText(installed)).toBeNull();
  });

  it('says the same in the Settings row', () => {
    expect(checkStatusText(installed, '0.2.5')).toBe(words);
  });
});
