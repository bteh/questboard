import { isDesktopApp } from '@/lib/platform';
import { downloadPercent, type UpdateState } from '@/lib/updater-logic';

const LAST_CHECK_KEY = 'questboard.updater.lastCheckedAt';

export function readLastCheckedAt(): number | null {
  try {
    const raw = window.localStorage.getItem(LAST_CHECK_KEY);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastCheckedAt(at: number): void {
  try {
    window.localStorage.setItem(LAST_CHECK_KEY, String(at));
  } catch {
    // A locked-down webview must not break the update path.
  }
}

/**
 * Look for an update and download it if there is one.
 *
 * Every failure here is silent by design: no endpoint, no network, an
 * unsigned payload, a half-published release. None of that is something
 * the user asked for or can act on, so it degrades to "no update".
 */
export async function fetchAndStageUpdate(
  onState: (state: UpdateState) => void,
): Promise<void> {
  if (!isDesktopApp()) return;

  try {
    const { check } = await import('@tauri-apps/plugin-updater');
    const update = await check();
    if (!update) return;

    let downloaded = 0;
    let total: number | null = null;
    onState({ kind: 'downloading', percent: 0 });

    await update.download((event) => {
      if (event.event === 'Started') {
        total = event.data.contentLength ?? null;
      } else if (event.event === 'Progress') {
        downloaded += event.data.chunkLength;
        onState({ kind: 'downloading', percent: downloadPercent(downloaded, total) });
      }
    });

    onState({ kind: 'ready', version: update.version });
  } catch (err) {
    console.warn('update check failed', err);
    onState({ kind: 'failed' });
  }
}

/**
 * Install the staged update and relaunch.
 *
 * The backend is shut down first on purpose. It owns an open SQLite file
 * and a listening port, and letting the process group die on its own
 * during a relaunch races the new instance for both.
 */
export async function installAndRestart(): Promise<void> {
  const { invoke } = await import('@tauri-apps/api/core');
  const { check } = await import('@tauri-apps/plugin-updater');
  const { relaunch } = await import('@tauri-apps/plugin-process');

  const update = await check();
  if (!update) return;

  await invoke('shutdown_runtime_for_update');
  await update.install();
  await relaunch();
}
