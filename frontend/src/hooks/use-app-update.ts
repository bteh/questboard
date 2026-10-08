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
import { readUpdateState, setUpdateState, useUpdateState } from '@/lib/updater-store';

/**
 * Keep the desktop app current without ever interrupting the user.
 *
 * Mounted once, by the topbar pill. Every launch checks after the board has
 * painted. An open app looks again every half hour and when the reader comes
 * back to the window, but never twice within RECHECK_AFTER_MS, and never once
 * an update is already downloading or waiting on a restart.
 */
export function useAppUpdate() {
  const state = useUpdateState();

  useEffect(() => {
    if (!isDesktopApp()) return;

    const check = () => {
      if (!shouldCheck(null, Date.now(), readUpdateState())) return;
      writeLastCheckedAt(Date.now());
      void fetchAndStageUpdate(setUpdateState);
    };
    const throttled = () => {
      if (!shouldCheck(readLastCheckedAt(), Date.now(), readUpdateState())) return;
      check();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') throttled();
    };

    const settle = window.setTimeout(check, 4000);
    const interval = window.setInterval(throttled, CHECK_INTERVAL_MS);
    window.addEventListener('focus', throttled);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearTimeout(settle);
      window.clearInterval(interval);
      window.removeEventListener('focus', throttled);
      document.removeEventListener('visibilitychange', onVisible);
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
