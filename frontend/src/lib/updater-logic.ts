/**
 * Update state and the words the user reads. No Tauri, no network, no clock.
 *
 * Updates are meant to be boring: Questboard checks quietly, downloads
 * quietly, and only speaks up once a new version is sitting on disk ready
 * to go. A failed check is not the user's problem, so it stays silent.
 */

export type UpdateState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'up_to_date' }
  | { kind: 'downloading'; percent: number }
  | { kind: 'ready'; version: string }
  | { kind: 'installing'; version: string }
  | { kind: 'install_failed'; version: string }
  /* the new bundle is on disk but the relaunch did not happen; only a
     manual quit and reopen finishes it */
  | { kind: 'installed'; version: string }
  | { kind: 'failed' };

/** How often an open app wakes up to look for a release. */
export const CHECK_INTERVAL_MS = 30 * 60 * 1000;

/** The one throttle: no check within this long of the last one, whatever
 *  asked for it (the timer, or the reader coming back to the window). */
export const RECHECK_AFTER_MS = 15 * 60 * 1000;

/** Past these states a check would only restart work already done or under way. */
export function isUpdateBusy(state: UpdateState): boolean {
  switch (state.kind) {
    case 'checking':
    case 'downloading':
    case 'ready':
    case 'installing':
    case 'install_failed':
    case 'installed':
      return true;
    case 'idle':
    case 'up_to_date':
    case 'failed':
      return false;
  }
}

/**
 * Throttle for the timer and window focus. Every launch checks regardless
 * of time: a person who quits and reopens the app to "see the update" must
 * see it, and the check is one small file.
 */
export function shouldCheck(
  lastCheckedAt: number | null,
  now: number,
  state: UpdateState = { kind: 'idle' },
): boolean {
  if (isUpdateBusy(state)) return false;
  if (lastCheckedAt === null) return true;
  return now - lastCheckedAt >= RECHECK_AFTER_MS;
}

function installedText(version: string): string {
  return `Installed ${version}. Quit and reopen Questboard to finish.`;
}

/** Text for the explicit "Check for updates" row in Settings. Unlike the
 *  topbar pill, this one is allowed to say "nothing to do". */
export function checkStatusText(state: UpdateState, currentVersion: string): string {
  switch (state.kind) {
    case 'checking':
      return 'Checking…';
    case 'up_to_date':
      return `You have the latest version, ${currentVersion}.`;
    case 'downloading':
      return `Downloading the update… ${state.percent}%`;
    case 'ready':
      return `Version ${state.version} is downloaded. Restart to use it.`;
    case 'installing':
      return `Installing ${state.version}…`;
    case 'install_failed':
      return `Couldn't install ${state.version}. Try again, or download it from the website.`;
    case 'installed':
      return installedText(state.version);
    case 'failed':
      return 'Could not reach the update server. Check your connection and try again.';
    case 'idle':
      return `Questboard ${currentVersion}`;
  }
}

/** Null means show nothing at all. */
export function updateBannerText(state: UpdateState): string | null {
  switch (state.kind) {
    case 'ready':
      return 'Update ready';
    case 'installing':
      return `Installing ${state.version}…`;
    case 'install_failed':
      return `Couldn't install ${state.version}. The app still works.`;
    case 'installed':
      return installedText(state.version);
    case 'downloading':
      // A percentage that only moves on a fast connection reads as broken,
      // so the download stays wordless until it lands.
      return null;
    case 'checking':
    case 'up_to_date':
    case 'failed':
    case 'idle':
      return null;
  }
}

/** The full sentence for screen readers and the hover title; the pill
 *  itself drops the version to stay short. */
export function updateBannerLabel(state: UpdateState): string | null {
  if (state.kind === 'ready') return `Version ${state.version} is ready. Restart to update.`;
  return updateBannerText(state);
}

/** The word on the pill's button. Null means nothing to click. */
export function updateActionText(state: UpdateState): string | null {
  switch (state.kind) {
    case 'ready':
      return 'Restart';
    case 'install_failed':
      return 'Try again';
    case 'installed':
    case 'installing':
    case 'downloading':
    case 'checking':
    case 'up_to_date':
    case 'failed':
    case 'idle':
      return null;
  }
}

export function downloadPercent(downloaded: number, total: number | null): number {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((downloaded / total) * 100));
}
