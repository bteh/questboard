/**
 * Update state and the words the user reads. No Tauri, no network, no clock.
 *
 * Updates are meant to be boring: Questboard checks quietly, downloads
 * quietly, and only speaks up once a new version is sitting on disk ready
 * to go. A failed check is not the user's problem, so it stays silent.
 */

export type UpdateState =
  | { kind: 'idle' }
  | { kind: 'downloading'; percent: number }
  | { kind: 'ready'; version: string }
  | { kind: 'failed' };

export const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

/**
 * A missed check is cheap and a doubled check is wasteful, so a machine
 * that was asleep for a week still only checks once on wake.
 */
export function shouldCheck(lastCheckedAt: number | null, now: number): boolean {
  if (lastCheckedAt === null) return true;
  return now - lastCheckedAt >= CHECK_INTERVAL_MS;
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
    case 'failed':
    case 'idle':
      return null;
  }
}

export function downloadPercent(downloaded: number, total: number | null): number {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((downloaded / total) * 100));
}
