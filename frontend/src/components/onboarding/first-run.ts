/* The first-run hand-off flag, pinned by first-run.test.ts. One writer,
   one reader, one key: the onboarding wizard marks the flag when the
   reader saves their first preferences, and the board's Find work lane
   consumes it on mount to pull the first jobs once, so a brand-new user
   lands on a lane that fills itself in. Storage access follows lib/entry.ts:
   every read and write in try/catch, a locked-down browser just skips the
   hand-off. */

const FIRST_RUN_PENDING_KEY = 'questboard:first-run-pending';
/* an older build wrote this key and nothing ever read it */
const ORPHANED_COMPLETE_KEY = 'questboard:onboarding-complete';

export function markFirstRunPending(): void {
  try {
    window.localStorage.setItem(FIRST_RUN_PENDING_KEY, '1');
    window.localStorage.removeItem(ORPHANED_COMPLETE_KEY);
  } catch {
    /* storage refused: the hand-off skips, nothing breaks */
  }
}

export function consumeFirstRunPending(): boolean {
  try {
    const pending = window.localStorage.getItem(FIRST_RUN_PENDING_KEY) === '1';
    if (pending) window.localStorage.removeItem(FIRST_RUN_PENDING_KEY);
    return pending;
  } catch {
    return false;
  }
}
