/* The entered flag: once someone has been inside the app, the front door
   at / stops showing them the pitch. Key follows the existing
   questboard:first-run-pending convention; every read and write sits in
   try/catch the way search.tsx already does, so a locked-down browser
   just sees the landing again. */

export const ENTERED_KEY = 'questboard:entered';

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

/* Where / sends a returner. PR 3 flips this to '/home' once the masthead
   home page exists; until then returners land on the board itself. */
export function entryRedirectTarget(): '/board' | null {
  return hasEntered() ? '/board' : null;
}
