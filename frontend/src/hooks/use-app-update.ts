import { useCallback, useEffect, useState } from 'react';

import { isDesktopApp } from '@/lib/platform';
import {
  fetchAndStageUpdate,
  installAndRestart,
  readLastCheckedAt,
  writeLastCheckedAt,
} from '@/lib/updater';
import { CHECK_INTERVAL_MS, shouldCheck, type UpdateState } from '@/lib/updater-logic';

/**
 * Keep the desktop app current without ever interrupting the user.
 *
 * The check runs after the board has painted, not during boot, because a
 * cold start already costs the user seconds and an update is never urgent.
 */
export function useAppUpdate() {
  const [state, setState] = useState<UpdateState>({ kind: 'idle' });

  useEffect(() => {
    if (!isDesktopApp()) return;

    let cancelled = false;
    const guardedSetState = (next: UpdateState) => {
      if (!cancelled) setState(next);
    };

    const run = () => {
      if (!shouldCheck(readLastCheckedAt(), Date.now())) return;
      writeLastCheckedAt(Date.now());
      void fetchAndStageUpdate(guardedSetState);
    };

    const settle = window.setTimeout(run, 4000);
    const interval = window.setInterval(run, CHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(settle);
      window.clearInterval(interval);
    };
  }, []);

  const restart = useCallback(() => {
    void installAndRestart();
  }, []);

  return { state, restart };
}
