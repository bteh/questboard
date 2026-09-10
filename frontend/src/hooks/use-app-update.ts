import { useCallback, useEffect, useState } from 'react';

import { isDesktopApp } from '@/lib/platform';
import {
  currentAppVersion,
  fetchAndStageUpdate,
  installAndRestart,
  readLastCheckedAt,
  writeLastCheckedAt,
} from '@/lib/updater';
import { CHECK_INTERVAL_MS, shouldCheck } from '@/lib/updater-logic';
import { setUpdateState, useUpdateState } from '@/lib/updater-store';

/**
 * Keep the desktop app current without ever interrupting the user.
 *
 * Mounted once, by the topbar pill. Every launch checks after the board has
 * painted; the six-hour throttle only guards the background timer, so a
 * machine waking from a long sleep does not fire a burst of checks.
 */
export function useAppUpdate() {
  const state = useUpdateState();

  useEffect(() => {
    if (!isDesktopApp()) return;

    const check = () => {
      writeLastCheckedAt(Date.now());
      void fetchAndStageUpdate(setUpdateState);
    };
    const throttled = () => {
      if (!shouldCheck(readLastCheckedAt(), Date.now())) return;
      check();
    };

    const settle = window.setTimeout(check, 4000);
    const interval = window.setInterval(throttled, CHECK_INTERVAL_MS);
    return () => {
      window.clearTimeout(settle);
      window.clearInterval(interval);
    };
  }, []);

  const restart = useCallback(() => {
    void installAndRestart(setUpdateState);
  }, []);

  return { state, restart };
}

/** The explicit "Check for updates" row in Settings: no timers, same state. */
export function useUpdateCheck() {
  const state = useUpdateState();
  const [version, setVersion] = useState('');

  useEffect(() => {
    void currentAppVersion().then(setVersion);
  }, []);

  const checkNow = useCallback(() => {
    if (!isDesktopApp()) return;
    writeLastCheckedAt(Date.now());
    void fetchAndStageUpdate(setUpdateState);
  }, []);

  const restart = useCallback(() => {
    void installAndRestart(setUpdateState);
  }, []);

  return { state, version, checkNow, restart };
}
