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
  | { kind: 'failed' };

export const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

/**
 * Throttle for the background timer only. Every launch checks regardless:
 * a person who quits and reopens the app to "see the update" must see it,
 * and the check is one small file. The timer is what a sleeping machine
 * would otherwise fire many times on wake.
 */
export function shouldCheck(lastCheckedAt: number | null, now: number): boolean {
  if (lastCheckedAt === null) return true;
  return now - lastCheckedAt >= CHECK_INTERVAL_MS;
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
      return `Version ${state.version} is ready.`;
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

export function downloadPercent(downloaded: number, total: number | null): number {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((downloaded / total) * 100));
}
