/* The entered flag: once someone has been inside the app, the front door
   at / stops showing them the pitch. Key follows the existing
   questboard:first-run-pending convention; every read and write sits in
   try/catch the way search.tsx already does, so a locked-down browser
   just sees the landing again. */

export const ENTERED_KEY = 'questboard:entered';

/* The onboarded flag: set once someone has picked a place (or explicitly
   skipped) on the first-run screen, so the one-question setup never asks
   twice. A returner's CTA goes straight to the board. */
export const ONBOARDED_KEY = 'questboard:onboarded';

export function hasEntered(): boolean {
  try {
    return window.localStorage.getItem(ENTERED_KEY) === '1';
  } catch {
    return false;
  }
}

export function markEntered(): void {
  try {
    window.localStorage.setItem(ENTERED_KEY, '1');
  } catch {
    /* storage refused: nothing breaks, the landing shows next visit */
  }
}

export function hasOnboarded(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDED_KEY) === '1';
  } catch {
    return false;
  }
}

export function markOnboarded(): void {
  try {
    window.localStorage.setItem(ONBOARDED_KEY, '1');
  } catch {
    /* storage refused: the place picker shows again next visit, harmless */
  }
}

/** Clear user-owned browser state while preserving the active auth/session. */
export function erasePersonalBrowserState(): void {
  try {
    const preservedPrefixes = [
      'questboard-local-workspace-session:',
      'questboard-dev-hosted-session',
    ];
    const keys = Array.from({ length: window.localStorage.length }, (_, index) =>
      window.localStorage.key(index),
    ).filter((key): key is string => Boolean(key));
    for (const key of keys) {
      const isQuestboardData = key.startsWith('questboard') || key.startsWith('qb-');
      const preserve = preservedPrefixes.some((prefix) => key.startsWith(prefix));
      if (isQuestboardData && !preserve) {
        window.localStorage.removeItem(key);
      }
    }
  } catch {
    /* storage refused: server-side erase still completed */
  }
}

/* Where / sends a returner: the masthead home, the subscriber's front page.
   The pitch never replays for a known reader. */
export function entryRedirectTarget(): '/home' | null {
  return hasEntered() ? '/home' : null;
}
