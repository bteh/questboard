import { useCallback, useState } from 'react';

import { useWorkspace } from '@/contexts/workspace-context';
import { useOnboardingState } from '@/hooks/use-workspace';

const STORAGE_KEY = 'launchboard:onboarding-complete';

function readPersisted(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writePersisted(value: boolean): void {
  try {
    if (value) {
      window.localStorage.setItem(STORAGE_KEY, '1');
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage unavailable — in-memory state still tracks it
  }
}

/**
 * Controls whether the onboarding wizard should pop on top of the current
 * route. The gate is designed so a brand-new user sees the wizard ONCE, and
 * once they've either completed it (preferences saved) or explicitly
 * dismissed it, it stays dismissed across reloads.
 *
 * Prior behavior was buggy: `shouldShow` was computed purely from the
 * server-side `has_started_search` flag, so a user who closed the wizard
 * without starting a search was trapped — the wizard re-appeared on every
 * route and every reload. That made the app feel broken for anyone who
 * didn't immediately follow the happy path (e.g. a non-technical user
 * who clicked "skip" and then looked around).
 *
 * Rules now:
 *   1. If the workspace server reports `has_started_search === true`,
 *      onboarding is DONE (the user already ran a search, no wizard ever).
 *   2. If the user has saved preferences (OnboardingWizard.handleSave fires
 *      `launchboard:onboarding-complete = "1"`), onboarding is DONE.
 *   3. If the user calls `dismiss()` (Skip from welcome step, X button, or
 *      the in-session state from OnboardingGate), onboarding is DONE.
 *   4. The `markIncomplete()` helper is exposed so a "Restart onboarding"
 *      button in Settings can reset the flag and bring the wizard back.
 */
export function useOnboarding() {
  const { isLoading: workspaceLoading } = useWorkspace();
  const { data, isLoading } = useOnboardingState(!workspaceLoading);
  // useState with a lazy initializer reads localStorage once per mount.
  // The wizard lives at the app root so this runs once per app load, which
  // is exactly what we want. Cross-tab sync isn't needed for a desktop app.
  const [persistedComplete, setPersistedComplete] = useState<boolean>(readPersisted);

  const dismiss = useCallback(() => {
    writePersisted(true);
    setPersistedComplete(true);
  }, []);

  const markIncomplete = useCallback(() => {
    writePersisted(false);
    setPersistedComplete(false);
  }, []);

  const serverSaysDone = !!data?.has_started_search;
  const ready = !workspaceLoading && !isLoading && !!data;

  return {
    shouldShow: ready && !serverSaysDone && !persistedComplete,
    dismiss,
    markIncomplete,
    isLoading: workspaceLoading || isLoading,
  };
}
